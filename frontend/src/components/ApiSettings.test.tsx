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

it("can create a token that never expires",async()=>{
  let issued=false;
  vi.mocked(api).mockImplementation(async(_path,method)=>{
    const token={id:"permanent",name:"Permanent client",created_at:"2026-10-17",expires_at:null};
    if(method==="POST"){issued=true;return {...token,token:"magpie_permanent"};}
    return issued?[token]:[];
  });
  render(<ApiSettings notify={vi.fn()}/>);
  await screen.findByText("No API tokens yet.");
  fireEvent.change(screen.getByLabelText("App name"),{target:{value:"Permanent client"}});
  fireEvent.click(screen.getByRole("checkbox",{name:"Never expires"}));
  expect(screen.getByLabelText("Expires in (days)")).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"Create token"}));
  await screen.findByLabelText("New API token");
  expect(api).toHaveBeenCalledWith("/tokens","POST",{name:"Permanent client",expires_days:null});
  expect(screen.getByText("Never expires",{selector:"small"})).toBeVisible();
});
