import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, it, expect, vi } from "vitest";
import PathPicker from "./PathPicker";
import { api } from "../services/api";
vi.mock("../services/api", () => ({ api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it("offers server folder suggestions while typing", async () => {
  vi.mocked(api).mockResolvedValue({ path: "/downloads", parent: "", folders: ["/downloads/pictures"], truncated: false });
  const change = vi.fn();
  render(<PathPicker value="/downloads/pi" onChange={change} disabled={false} />);
  await waitFor(() => expect(document.querySelector('option[value="/downloads/pictures"]')).toBeTruthy());
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "/downloads/pictures" } });
  expect(change).toHaveBeenCalledWith("/downloads/pictures");
});
it("disables browsing for an existing destination", () => {
  render(<PathPicker value="/downloads/pictures" onChange={vi.fn()} disabled />);
  expect(screen.getByRole("button", { name: "Browse folders" })).toBeDisabled();
});
