import asyncio
from app.database.store import Store
from app.downloads.queue import Queue,now

def insert(store,ident,status='queued'):
    store.execute('INSERT INTO jobs (id,url,website,destination_id,destination_name,destination_path,status,created_at) VALUES (?,?,?,?,?,?,?,?)',(ident,'https://example.com','example.com','dest','Pictures','/downloads',status,now()))
def test_fifo_concurrency_and_recovery(tmp_path):
    async def scenario():
        store=Store(tmp_path/'db.sqlite3')
        settings=store.get('settings');settings['concurrency']=2;store.set('settings',settings)
        for i in range(5):insert(store,str(i))
        insert(store,'interrupted','downloading')
        q=Queue(store,{'dir':tmp_path});started=[];running=0;peak=0
        async def execute(row,settings):
            nonlocal running,peak
            started.append(row['id']);running+=1;peak=max(peak,running)
            await asyncio.sleep(.15);running-=1
            store.execute("UPDATE jobs SET status='completed' WHERE id=?",(row['id'],))
        q.execute=execute
        await q.start();await asyncio.sleep(.9);await q.stop()
        assert started==['0','1','2','3','4'];assert peak==2
        assert store.one("SELECT status FROM jobs WHERE id='interrupted'")['status']=='interrupted'
    asyncio.run(scenario())
def test_process_group_cancellation():
    import sys
    from app.downloads.queue import terminate
    async def scenario():
        p=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(60)',start_new_session=True)
        await terminate(p)
        assert p.returncode is not None
    asyncio.run(scenario())

def test_running_cancellation_timeout_and_shutdown(tmp_path,monkeypatch):
    import sys
    original=asyncio.create_subprocess_exec
    async def fake_engine(*args,**kwargs):
        # Real child process with controlled work; production lifecycle management.
        return await original(sys.executable,'-c',"import json,sys,time;sys.stdin.readline();print(json.dumps({'files':1,'bytes':14}),flush=True);time.sleep(30)",**kwargs)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',fake_engine)
    async def scenario(mode):
        base=tmp_path/mode;base.mkdir();root=base/'media';root.mkdir()
        store=Store(base/'db.sqlite3');insert(store,'test')
        store.execute('UPDATE jobs SET destination_path=?',(str(root),))
        q=Queue(store,{'dir':base,'roots':[root],'job_timeout':.1 if mode=='timeout' else 60})
        await q.start()
        for _ in range(100):
            if store.one('SELECT files FROM jobs')['files']:break
            await asyncio.sleep(.02)
        assert store.one('SELECT files FROM jobs')['files']==1
        if mode=='cancel':store.execute('UPDATE jobs SET cancel_requested=1')
        if mode=='shutdown':await q.stop()
        else:
            for _ in range(100):
                if store.one('SELECT status FROM jobs')['status']!='downloading':break
                await asyncio.sleep(.02)
            await q.stop()
        status=store.one('SELECT status FROM jobs')['status']
        assert status=={'cancel':'cancelled','timeout':'failed','shutdown':'interrupted'}[mode]
        assert not q.active
    for mode in ('cancel','timeout','shutdown'):asyncio.run(scenario(mode))
