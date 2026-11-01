import { render,screen,fireEvent,waitFor,cleanup } from '@testing-library/react';
import { afterEach,it,expect,vi } from 'vitest';
import DownloadForm from './DownloadForm';
import { api } from '../services/api';
vi.mock('../services/api',()=>({api:vi.fn()}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
const destination={id:'pictures',name:'Pictures',path:'/downloads/pictures',description:'',icon:'folder',is_default:true,organisation:'inherit',accessible:true,writable:true} as const;
function form(){const created=vi.fn();render(<DownloadForm destinations={[destination]} onCreated={created} onManage={vi.fn()}/>);fireEvent.change(screen.getByLabelText('What caught your eye?'),{target:{value:'https://example.com/gallery'}});return created;}
it.each([['Prefix','start'],['Suffix','end']])('sends a %s tag through the existing filename API',async(_,position)=>{
 vi.mocked(api).mockResolvedValue({});const created=form();
 fireEvent.change(screen.getByLabelText(/Tag \(optional\)/),{target:{value:'  Nature  '}});
 fireEvent.change(screen.getByLabelText('Position'),{target:{value:position}});
 fireEvent.click(screen.getByRole('button',{name:'Pluck'}));
 await waitFor(()=>expect(created).toHaveBeenCalledOnce());
 expect(api).toHaveBeenCalledWith('/downloads','POST',{url:'https://example.com/gallery',destination_id:'pictures',custom_fields:{tag:'Nature'},filename_position:position});
 expect(screen.getByLabelText(/Tag \(optional\)/)).toHaveValue('');
 expect(screen.getByLabelText('What caught your eye?')).toHaveValue('');
 expect(screen.getByLabelText('Position')).toHaveValue(position);
});
it('keeps an empty tag optional and supports Enter submission',async()=>{
 vi.mocked(api).mockResolvedValue({});const created=form();
 fireEvent.change(screen.getByLabelText(/Tag \(optional\)/),{target:{value:'   '}});
 fireEvent.submit(screen.getByRole('button',{name:'Pluck'}).closest('form')!);
 await waitFor(()=>expect(created).toHaveBeenCalledOnce());
 expect(api).toHaveBeenCalledWith('/downloads','POST',{url:'https://example.com/gallery',destination_id:'pictures'});
});
it('retains the tag and position if queue submission fails',async()=>{
 vi.mocked(api).mockRejectedValue(new Error('Queue full'));form();
 fireEvent.change(screen.getByLabelText(/Tag \(optional\)/),{target:{value:'Keep me'}});
 fireEvent.change(screen.getByLabelText('Position'),{target:{value:'end'}});
 fireEvent.click(screen.getByRole('button',{name:'Pluck'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Queue full');
 expect(screen.getByLabelText(/Tag \(optional\)/)).toHaveValue('Keep me');
 expect(screen.getByLabelText('Position')).toHaveValue('end');
});
