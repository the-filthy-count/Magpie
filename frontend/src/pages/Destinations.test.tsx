import { render,screen,fireEvent,waitFor,cleanup } from "@testing-library/react";
import { afterEach,it,expect,vi } from "vitest";
import Destinations from "./Destinations";
import { api } from "../services/api";
vi.mock('../services/api',()=>({api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('allows editing an existing container path and sends it when saved',async()=>{
 vi.mocked(api).mockResolvedValue({roots:['/downloads']});
 render(<Destinations destinations={[{id:'pictures',name:'Pictures',path:'/downloads/pictures',description:'',icon:'folder',organisation:'inherit',writable:true,accessible:true,is_default:true}]} reload={vi.fn().mockResolvedValue(undefined)} notify={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Edit Pictures'}));
 const path=screen.getByLabelText('Container path');
 expect(path).not.toBeDisabled();
 expect(screen.getByRole('button',{name:'Browse folders'})).not.toBeDisabled();
 fireEvent.change(path,{target:{value:'/downloads/new'}});
 fireEvent.click(screen.getByRole('button',{name:'Save destination'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/destinations/pictures','PATCH',expect.objectContaining({path:'/downloads/new'})));
});
