import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, beforeAll, it, expect, vi } from "vitest";
import DestinationPicker from "./DestinationPicker";
const destinations = [
  {id:"pictures", name:"Pictures", path:"/downloads/pictures", icon:"image", writable:true, accessible:true, description:"", is_default:true},
  {id:"offline", name:"Offline", path:"/downloads/offline", icon:"folder", writable:false, accessible:false, description:"", is_default:false},
  {id:"music", name:"Music", path:"/downloads/music", icon:"music", writable:true, accessible:true, description:"", is_default:false},
];
beforeAll(() => { Element.prototype.scrollIntoView = vi.fn(); });
afterEach(cleanup);
it("opens a themed menu and selects a destination", () => {
  const change = vi.fn();
  render(<DestinationPicker destinations={destinations} value="pictures" onChange={change} />);
  fireEvent.click(screen.getByRole("combobox"));
  expect(screen.getByRole("listbox")).toBeVisible();
  fireEvent.click(screen.getByRole("option", {name:/Music/}));
  expect(change).toHaveBeenCalledWith("music");
  expect(screen.queryByRole("listbox")).toBeNull();
});
it("supports keyboard selection, skips unavailable folders and closes on Escape", () => {
  const change = vi.fn();
  render(<DestinationPicker destinations={destinations} value="pictures" onChange={change} />);
  const trigger = screen.getByRole("combobox");
  fireEvent.keyDown(trigger,{key:"ArrowDown"});
  fireEvent.keyDown(trigger,{key:"ArrowDown"});
  fireEvent.keyDown(trigger,{key:"Enter"});
  expect(change).toHaveBeenCalledWith("music");
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("option", {name:/Offline/}));
  expect(change).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(trigger,{key:"Escape"});
  expect(screen.queryByRole("listbox")).toBeNull();
});
