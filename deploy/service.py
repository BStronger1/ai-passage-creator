#!/usr/bin/env python3
"""Run the Python/Vue application with an isolated MariaDB and Redis (Linux)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'app'
BIN = ROOT / 'runtime/bin'
CONF = ROOT / 'supervisord.conf'
MYSQLD = BIN / 'mariadbd' if (BIN / 'mariadbd').exists() else Path('/usr/sbin/mysqld')
MYSQL_INSTALL = BIN / 'mariadb-install-db' if (BIN / 'mariadb-install-db').exists() else Path('/usr/bin/mysql_install_db')
MYSQL_BASE = ROOT / 'runtime' if MYSQLD.parent == BIN else Path('/usr')


def write_private(path, text):
    path.write_text(text, encoding='utf-8')
    path.chmod(0o600)


def ctl(*args, check=True):
    return subprocess.run([str(BIN / 'supervisorctl'), '-c', str(CONF), *args], check=check)


def setup(bind):
    import pymysql
    os.umask(0o077)
    for directory in ['logs', 'run', 'data/mysql', 'data/redis']:
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    private = ROOT / 'secrets.json'
    if private.exists():
        credentials = json.loads(private.read_text())
    else:
        credentials = {name: secrets.token_hex(24) for name in ['db_password', 'root_password', 'redis_password', 'session_key', 'admin_password']}
        credentials['admin_account'] = 'yangbin'
        write_private(private, json.dumps(credentials, indent=2))
    env_path = APP / 'python-backend/.env'
    if not env_path.exists():
        env = {
            'DB_HOST':'127.0.0.1', 'DB_PORT':'13307', 'DB_NAME':'ai_passage_creator',
            'DB_USER':'yangbin', 'DB_PASSWORD':credentials['db_password'],
            'REDIS_HOST':'127.0.0.1', 'REDIS_PORT':'16380', 'REDIS_DB':'0',
            'REDIS_PASSWORD':credentials['redis_password'],
            'SESSION_SECRET_KEY':credentials['session_key'], 'PASSWORD_SALT':'yangbin',
            'DASHSCOPE_API_KEY':'not-configured', 'DASHSCOPE_MODEL':'qwen-plus',
            'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'PEXELS_API_KEY':'', 'NANO_BANANA_API_KEY':'', 'TENCENT_COS_SECRET_ID':'',
            'TENCENT_COS_SECRET_KEY':'', 'TENCENT_COS_REGION':'ap-guangzhou',
            'TENCENT_COS_BUCKET':'', 'STRIPE_API_KEY':'', 'STRIPE_WEBHOOK_SECRET':''
        }
        write_private(env_path, ''.join(f'{key}={value}\n' for key,value in env.items()))
    socket = ROOT / 'run/mysql.sock'
    mysql_conf = ROOT / 'mysql.cnf'
    write_private(mysql_conf, f'''[mysqld]
basedir={MYSQL_BASE}
datadir={ROOT / 'data/mysql'}
socket={socket}
pid-file={ROOT / 'run/mysql.pid'}
port=13307
bind-address=127.0.0.1
skip-name-resolve
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
innodb-buffer-pool-size=128M
log-error={ROOT / 'logs/mysql-error.log'}
''')
    write_private(ROOT / 'redis.conf', f'''bind 127.0.0.1
port 16380
requirepass {credentials['redis_password']}
dir {ROOT / 'data/redis'}
appendonly yes
maxmemory 128mb
maxmemory-policy noeviction
''')
    if not (ROOT / 'data/mysql/mysql').is_dir():
        subprocess.run([str(MYSQL_INSTALL), '--no-defaults', f'--basedir={MYSQL_BASE}', f'--datadir={ROOT / "data/mysql"}', '--auth-root-authentication-method=normal', '--skip-test-db'], check=True, stdout=subprocess.DEVNULL)
    if not (ROOT / 'data/schema-ready').exists():
        db_process = subprocess.Popen([str(MYSQLD), f'--defaults-file={mysql_conf}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        conn = None
        try:
            for _ in range(90):
                try:
                    conn = pymysql.connect(unix_socket=str(socket), user='root', password='', charset='utf8mb4', autocommit=True, client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS)
                    break
                except pymysql.err.OperationalError:
                    if db_process.poll() is not None:
                        raise RuntimeError('MariaDB startup failed; inspect logs/mysql-error.log')
                    time.sleep(1)
            if conn is None:
                raise RuntimeError('MariaDB startup timed out')
            with conn.cursor() as cursor:
                for filename in ['create_table.sql', 'update_quota.sql', 'add_phase_fields.sql', 'add_article_style.sql', 'add_vip_payment.sql']:
                    cursor.execute((APP/'sql'/filename).read_text(encoding='utf-8'))
                    while cursor.nextset():
                        pass
                cursor.execute('DELETE FROM user WHERE id IN (1,2,3)')
                digest = hashlib.md5((credentials['admin_password']+'yangbin').encode()).hexdigest()
                cursor.execute('INSERT INTO user (userAccount,userPassword,userName,userRole,quota) VALUES (%s,%s,%s,%s,%s)', ('yangbin',digest,'yangbin','admin',100))
                cursor.execute("CREATE USER IF NOT EXISTS 'yangbin'@'127.0.0.1' IDENTIFIED BY %s", (credentials['db_password'],))
                cursor.execute("GRANT ALL PRIVILEGES ON ai_passage_creator.* TO 'yangbin'@'127.0.0.1'")
                cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (credentials['root_password'],))
                cursor.execute("SELECT User,Host FROM mysql.user WHERE User=''")
                for user, host in cursor.fetchall():
                    cursor.execute('DROP USER %s@%s', (user,host))
                # Local bootstrap accounts must not retain empty passwords.
                cursor.execute('SELECT User,Host FROM mysql.user WHERE User=%s', ('root',))
                for _, host in cursor.fetchall():
                    if host != 'localhost':
                        cursor.execute('DROP USER %s@%s', ('root',host))
                (ROOT/'data/schema-ready').write_text('1\n')
        finally:
            if conn is not None:
                conn.close()
            db_process.terminate()
            db_process.wait(timeout=30)
    config = f'''[unix_http_server]
file={ROOT / 'run/supervisor.sock'}
chmod=0600
[supervisord]
logfile={ROOT / 'logs/supervisord.log'}
pidfile={ROOT / 'run/supervisord.pid'}
childlogdir={ROOT / 'logs'}
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix://{ROOT / 'run/supervisor.sock'}
[program:mysql]
command={MYSQLD} --defaults-file={mysql_conf}
autostart=true
autorestart=true
priority=10
stdout_logfile={ROOT / 'logs/mysql.log'}
redirect_stderr=true
stopwaitsecs=30
[program:redis]
command={BIN / 'redis-server'} {ROOT / 'redis.conf'}
autostart=true
autorestart=true
priority=10
stdout_logfile={ROOT / 'logs/redis.log'}
redirect_stderr=true
[program:api]
command={APP / 'python-backend/.venv/bin/python'} -m uvicorn app.main:app --host {bind} --port 18567 --workers 1
 directory={APP / 'python-backend'}
autostart=true
autorestart=true
startsecs=5
startretries=10
priority=20
environment=PYTHONUNBUFFERED="1"
stdout_logfile={ROOT / 'logs/api.log'}
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
redirect_stderr=true
stopasgroup=true
killasgroup=true
'''.replace('\n directory=', '\ndirectory=')
    write_private(CONF, config)
    start()
    print('Setup complete. Private account credentials: ' + str(private))


def start():
    if (ROOT/'run/supervisor.sock').exists():
        result = ctl('status', check=False)
        if result.returncode in (0,3):
            ctl('start','all')
            return
    subprocess.run([str(BIN/'supervisord'), '-c', str(CONF)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['setup','start','stop','status','restart'])
    parser.add_argument('--bind', default='127.0.0.1')
    args = parser.parse_args()
    if args.action == 'setup':
        setup(args.bind)
    elif args.action == 'start':
        start()
    elif args.action == 'stop':
        ctl('shutdown')
    elif args.action == 'restart':
        ctl('restart', 'api')
    else:
        ctl('status')
