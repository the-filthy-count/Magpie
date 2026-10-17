import { render,screen,fireEvent,cleanup } from "@testing-library/react";
import { afterEach,it,expect } from "vitest";
import HelpTooltip from "./HelpTooltip";
afterEach(cleanup);
it("describes the shield on hover and keyboard focus and dismisses on Escape",()=>{
  render(<HelpTooltip label="Storage information" icon={<span/>}>Downloaded files are kept.</HelpTooltip>);
  expect(screen.queryByRole("tooltip")).toBeNull();
  const button=screen.getByRole("button",{name:"Storage information"});
  fireEvent.mouseEnter(button.parentElement!);
  expect(screen.getByRole("tooltip")).toHaveTextContent("Downloaded files are kept.");
  expect(button).toHaveAttribute("aria-describedby",screen.getByRole("tooltip").id);
  fireEvent.mouseLeave(button.parentElement!);
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.focus(button);
  expect(screen.getByRole("tooltip")).toBeVisible();
  fireEvent.keyDown(button,{key:"Escape"});
  expect(screen.queryByRole("tooltip")).toBeNull();
});
it("opens on tap and closes when tapping elsewhere",()=>{
  render(<HelpTooltip label="Storage information" icon={<span/>}>Downloaded files are kept.</HelpTooltip>);
  fireEvent.click(screen.getByRole("button"));
  expect(screen.getByRole("tooltip")).toBeVisible();
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("tooltip")).toBeNull();
});
