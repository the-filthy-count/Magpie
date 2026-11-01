import { render,screen,fireEvent,waitFor,cleanup } from '@testing-library/react';
import { afterEach,beforeEach,it,expect,vi } from 'vitest';
import JobTagEditor from './JobTagEditor';
import { api,Job } from '../services/api';
vi.mock('../services/api',()=>({api:vi.fn()}));
beforeEach(()=>{HTMLDialogElement.prototype.showModal=vi.fn(function(this:HTMLDialogElement){this.setAttribute('open','');});});
afterEach(()=>{cleanup();vi.resetAllMocks();});
const job:Job={id:'job',custom_fields:{creator:'Alice',tag:'Old'},filename_position:'start',status:'downloading',url:'https://example.com/file.png',website:'example.com',destination_id:'pictures',destination_name:'Pictures',destination_path:'/downloads/pictures',created_at:'2026-11-01T12:00:00Z',started_at:null,completed_at:null,files:0,skipped:0,bytes:0,speed:null,current_filename:null,file_bytes:null,file_total:null,error:null,attempts:1};
it('updates a downloading job while preserving other API fields',async()=>{
 vi.mocked(api).mockResolvedValue({});const saved=vi.fn(),close=vi.fn();render(<JobTagEditor job={job} onSaved={saved} onClose={close}/>);
 fireEvent.change(screen.getByLabelText('Tag (optional)'),{target:{value:'New'}});
 fireEvent.change(screen.getByLabelText('Position'),{target:{value:'end'}});
 fireEvent.click(screen.getByRole('button',{name:'Save tag'}));
 await waitFor(()=>expect(saved).toHaveBeenCalledOnce());
 expect(api).toHaveBeenCalledWith('/downloads/job','PATCH',{custom_fields:{creator:'Alice',tag:'New'},filename_position:'end'});
 expect(close).toHaveBeenCalledOnce();
});
it('removes just the tag when cleared and displays server conflicts',async()=>{
 vi.mocked(api).mockRejectedValue(new Error('Filename tags are locked once publication starts'));render(<JobTagEditor job={job} onSaved={vi.fn()} onClose={vi.fn()}/>);
 fireEvent.change(screen.getByLabelText('Tag (optional)'),{target:{value:'   '}});
 fireEvent.click(screen.getByRole('button',{name:'Save tag'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('locked');
 expect(api).toHaveBeenCalledWith('/downloads/job','PATCH',{custom_fields:{creator:'Alice'},filename_position:'start'});
});
