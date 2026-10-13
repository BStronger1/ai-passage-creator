const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
 const login=JSON.parse(fs.readFileSync(root+'/secrets.json','utf8'));
 const url='http://127.0.0.1:18567';
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];
 const results={login:true,sessionRefresh:true,articleList:true,createPage:true};
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url+'/user/login',{waitUntil:'networkidle'});
 await page.getByPlaceholder('请输入账号',{exact:true}).fill(login.admin_account);
 await page.getByPlaceholder('请输入密码',{exact:true}).fill(login.admin_password);
 await page.locator('button[type="submit"]').click();
 await page.waitForURL(url+'/',{timeout:30000});
 await page.goto(url+'/article/list',{waitUntil:'networkidle'});
 await page.screenshot({path:root+'/article-list.png',fullPage:true});
 await page.reload({waitUntil:'networkidle'});
 if(page.url().includes('/user/login'))throw Error('Session lost after refresh');
 const user=await page.evaluate(()=>fetch('/api/user/get/login').then(r=>r.json()));
 if(user.code!==0||user.data.userAccount!=='yangbin')throw Error('Browser login failed');
 await page.goto(url+'/create',{waitUntil:'networkidle'});
 await page.screenshot({path:root+'/create-page.png',fullPage:true});
 if(fs.existsSync(root+'/verification.json')) {
  const evidence=JSON.parse(fs.readFileSync(root+'/verification.json','utf8'));
  if(evidence.task_id) {
   await page.goto(url+'/article/'+evidence.task_id,{waitUntil:'networkidle'});
   await page.locator('.main-title').waitFor();
   const downloadPromise=page.waitForEvent('download');
   await page.getByRole('button',{name:'导出 Markdown'}).click();
   const download=await downloadPromise;
   await download.saveAs(root+'/browser-export.md');
   if(fs.statSync(root+'/browser-export.md').size<100)throw Error('Empty export');
   await page.screenshot({path:root+'/article-detail.png',fullPage:true});
   await page.mouse.move(700,700);
   await page.mouse.wheel(0,8000);
   await page.waitForFunction(()=>window.scrollY>0 || document.body.scrollTop>0);
   await page.screenshot({path:root+'/article-bottom.png'});
   results.longArticleScroll=true;
   results.articleDetail=true; results.markdownExport=true;
  }
 }
 if(errors.length) throw Error(errors.join('\n'));
 fs.writeFileSync(root+'/browser-verification.json',JSON.stringify({...results,pageErrors:errors},null,2));
 console.log('PASS browser checks: '+JSON.stringify(results)+'; no JavaScript errors.');
 await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
