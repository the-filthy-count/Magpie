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
