import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import { JobCard } from "./App";
import { bytes, Job } from "./services/api";
afterEach(cleanup);
const job: Job = {
  id: "a",
  url: "https://example.com/gallery",
  website: "example.com",
  destination_id: "b",
  destination_name: "Pictures",
  destination_path: "/downloads/pictures",
  status: "downloading",
  files: 3,
  skipped: 0,
  bytes: 2048,
  speed: null,
  current_filename: null,
  file_bytes: null,
  file_total: null,
  created_at: "2026-10-15T10:00:00Z",
  started_at: null,
  completed_at: null,
  error: null,
  attempts: 1,
};
describe("truthful job progress", () => {
  it("does not invent totals or speed", () => {
    const { container } = render(<JobCard job={job} action={vi.fn()} />);
    expect(container.querySelector(".indeterminate")).toBeTruthy();
    expect(screen.queryByText(/%|\/s/)).toBeNull();
    expect(screen.getByText("3 files")).toBeVisible();
  });
  it("shows measurable file progress", () => {
    render(
      <JobCard
        job={{ ...job, file_bytes: 50, file_total: 100, speed: 1024 }}
        action={vi.fn()}
      />,
    );
    expect(screen.getByText("Current file · 50%")).toBeVisible();
    expect(screen.getByText(/1.0 KB\/s/)).toBeVisible();
  });
  it("sends cancel and reveals destination details", () => {
    const action = vi.fn();
    render(<JobCard job={job} action={action} />);
    fireEvent.click(screen.getByLabelText("Cancel download"));
    expect(action).toHaveBeenCalledWith("/downloads/a/cancel");
    fireEvent.click(screen.getByLabelText("View details"));
    expect(screen.getByText("/downloads/pictures")).toBeVisible();
  });
  it("uses binary byte units", () => {
    expect(bytes(1024)).toBe("1.0 KB");
    expect(bytes(null)).toBe("—");
  });
});

it("shows album progress independently of the current file and includes archived files", () => {
  render(<JobCard job={{ ...job, files: 6, skipped: 2, total_files: 20, file_bytes: 22, file_total: 100 }} action={vi.fn()} />);
  expect(screen.getByLabelText("Current file progress")).toHaveAttribute("value", "22");
  expect(screen.getByLabelText("Album progress")).toHaveAttribute("value", "40");
  expect(screen.getByText("Album · 8 of 20 files · 2 skipped")).toBeVisible();
});
it("does not invent an album percentage when the total is unknown", () => {
  render(<JobCard job={job} action={vi.fn()} />);
  expect(screen.queryByLabelText("Album progress")).toBeNull();
  expect(screen.getByText("Overall · 3 files handled · total unknown")).toBeVisible();
});

it('mirrors file progress in the album bar for a single file',()=>{
 render(<JobCard job={{...job,files:0,skipped:0,total_files:1,file_bytes:37,file_total:100}} action={vi.fn()}/>);
 expect(screen.getByLabelText('Current file progress')).toHaveAttribute('value','37');
 expect(screen.getByLabelText('Album progress')).toHaveAttribute('value','37');
});
it('uses the API percentages in both progress bars',()=>{
 render(<JobCard job={{...job,files:0,total_files:1,file_progress_percent:42.5,album_progress_percent:42.5}} action={vi.fn()}/>);
 expect(screen.getByLabelText('Current file progress')).toHaveAttribute('value','42.5');
 expect(screen.getByLabelText('Album progress')).toHaveAttribute('value','42.5');
});
