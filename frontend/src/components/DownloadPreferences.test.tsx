import { render,screen,fireEvent,cleanup } from "@testing-library/react";
import { afterEach,it,expect,vi } from "vitest";
import DownloadPreferences from "./DownloadPreferences";
afterEach(cleanup);
const draft={video_quality:'best',video_format:'best',playlist:'all',media_filter:'extensions',extensions:['png'],max_files:0,max_file_size:0,subtitles:'manual',subtitle_languages:['en'],schedule_enabled:true,schedule_start:'22:00',schedule_end:'06:00',resume_interrupted:false,site_rules:[]};
it('updates video, file, schedule and recovery settings',()=>{
 const update=vi.fn();render(<DownloadPreferences draft={draft} update={update}/>);
 fireEvent.change(screen.getByLabelText('Maximum video quality'),{target:{value:'720'}});
 expect(update).toHaveBeenCalledWith('video_quality','720');
 fireEvent.change(screen.getByLabelText('Extensions (comma separated)'),{target:{value:'.jpg, webp'}});
 expect(update).toHaveBeenCalledWith('extensions',['jpg','webp']);
 fireEvent.click(screen.getByLabelText('Automatically retry interrupted jobs after restart'));
 expect(update).toHaveBeenCalledWith('resume_interrupted',true);
 fireEvent.change(screen.getByLabelText(/Maximum file size/),{target:{value:'10'}});
 expect(update).toHaveBeenCalledWith('max_file_size',10485760);
 fireEvent.change(screen.getByLabelText('Start time'),{target:{value:'23:00'}});
 expect(update).toHaveBeenCalledWith('schedule_start','23:00');
});
it('adds editable website defaults',()=>{
 const update=vi.fn();render(<DownloadPreferences draft={draft} update={update}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add website default'}));
 expect(update).toHaveBeenCalledWith('site_rules',[{website:''}]);
});
it('configures staging storage and direct publication',()=>{
 const update=vi.fn();render(<DownloadPreferences draft={{...draft,publish_when_complete:true,in_progress_path:''}} update={update}/>);
 fireEvent.change(screen.getByLabelText('In Progress location'),{target:{value:'/downloads/in-progress'}});
 expect(update).toHaveBeenCalledWith('in_progress_path','/downloads/in-progress');
 fireEvent.click(screen.getByLabelText('Publish only when the whole download completes'));
 expect(update).toHaveBeenCalledWith('publish_when_complete',false);
});
