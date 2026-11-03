import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import JobCard from './JobCard';
import type { Job } from '../services/api';
afterEach(cleanup);
const job = {id:'job',url:'https://example.com/album',website:'example.com',status:'failed',staging_path:'/downloads/in-progress/job',files:0,skipped:7,bytes:0,custom_fields:{},attempts:1} as Job;
it('offers manual publication only for failed staged jobs',()=>{
 const action=vi.fn().mockResolvedValue(undefined);
 const view=render(<JobCard job={job} action={action}/>);
 fireEvent.click(screen.getByRole('button',{name:'Finish with available files'}));
 expect(action).toHaveBeenCalledWith('/downloads/job/finish-available');
 view.rerender(<JobCard job={{...job,status:'downloading'}} action={action}/>);
 expect(screen.queryByRole('button',{name:'Finish with available files'})).toBeNull();
 view.rerender(<JobCard job={{...job,staging_path:''}} action={action}/>);
 expect(screen.queryByRole('button',{name:'Finish with available files'})).toBeNull();
});
it('distinguishes partial completion from a complete album',()=>{
 render(<JobCard job={{...job,status:'completed',finish_available:true,phase:'incomplete'}} action={vi.fn()}/>);
 expect(screen.getByText('Incomplete')).toBeTruthy();
});
