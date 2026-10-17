import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, it, expect, vi } from "vitest";
import ApiSettings from "./ApiSettings";
import { api } from "../services/api";
vi.mock("../services/api",()=>({api:vi.fn()}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it("creates a named token, shows it once and revokes it",async()=>{
  let issued=false;
  const token={id:"test",name:"Gallery client",created_at:"2026-10-17",expires_at:Date.now()/1000+86400};
  vi.mocked(api).mockImplementation(async (_path,method)=>{
    if(method==="POST"){issued=true;return {...token,token:"magpie_one_time_secret"};}
    if(method==="DELETE"){issued=false;return {ok:true};}
    return issued?[token]:[];
  });
  render(<ApiSettings notify={vi.fn()}/>);
  await screen.findByText("No API tokens yet.");
  fireEvent.change(screen.getByLabelText("App name"),{target:{value:"Gallery client"}});
  fireEvent.click(screen.getByRole("button",{name:"Create token"}));
  expect(await screen.findByLabelText("New API token")).toHaveValue("magpie_one_time_secret");
  fireEvent.click(screen.getByRole("button",{name:"Hide API token"}));
  expect(screen.queryByLabelText("New API token")).toBeNull();
  fireEvent.click(await screen.findByRole("button",{name:"Revoke Gallery client"}));
  await screen.findByText("No API tokens yet.");
  expect(api).toHaveBeenCalledWith("/tokens/test","DELETE");
});
