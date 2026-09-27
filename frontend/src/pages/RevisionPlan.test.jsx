import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import RevisionPlan from "./RevisionPlan";

const mockUseTrack = vi.fn();
vi.mock("../context/TrackContext", () => ({
  useTrack: () => mockUseTrack(),
}));

const mockGetRevisionPlan = vi.fn();
vi.mock("../api/progressApi", () => ({
  getRevisionPlan: (...args) => mockGetRevisionPlan(...args),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <RevisionPlan />
    </MemoryRouter>
  );
}

describe("RevisionPlan", () => {
  it("prompts for a track instead of crashing when none is selected", () => {
    mockUseTrack.mockReturnValue({ track: null });
    renderPage();
    expect(screen.getByText(/select a track/i)).toBeInTheDocument();
  });

  it("shows the empty-plan message when the backend reports no weak topics", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetRevisionPlan.mockResolvedValue({
      data: { plan: { track: "NEET", items: [{ message: "No weak topics detected -- keep practicing to maintain mastery." }] } },
    });
    renderPage();
    expect(await screen.findByText(/no weak topics detected/i)).toBeInTheDocument();
  });

  it("renders real revision items from an existing plan (real data, nothing fabricated)", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetRevisionPlan.mockResolvedValue({
      data: {
        plan: {
          track: "NEET",
          generated_at: "2026-09-27T14:51:00Z",
          items: [{ subject: "Biology", topic: "Cell", mastery: 20, attempts: 1, priority: "high" }],
        },
      },
    });
    renderPage();
    expect(await screen.findByText(/Cell/)).toBeInTheDocument();
    expect(screen.getByText(/high priority/i)).toBeInTheDocument();
  });

  it("shows a retry-able error instead of crashing when the API call fails", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetRevisionPlan.mockRejectedValue(new Error("network down"));
    renderPage();
    // getSafeErrorMessage (see utils/apiError.js) maps an error with no
    // .response -- a network failure, not a backend HTTPException -- to
    // this generic message rather than the fallback text passed in.
    expect(await screen.findByText(/unable to reach the server/i)).toBeInTheDocument();
  });

  it("reflects an updated plan on a fresh load rather than showing stale content forever", async () => {
    // Regression guard for the reported bug: the backend now regenerates a
    // stale plan (see backend/api/routes_progress.py's staleness check), and
    // this asserts the frontend has no client-side caching of its own that
    // would keep showing an old plan once the backend actually returns a
    // new one -- every mount/reload calls getRevisionPlan() fresh and
    // renders exactly what came back.
    mockUseTrack.mockReturnValue({ track: "NEET" });

    mockGetRevisionPlan.mockResolvedValueOnce({
      data: { plan: { track: "NEET", generated_at: "2026-09-27T14:51:00Z", items: [{ message: "No weak topics detected -- keep practicing to maintain mastery." }] } },
    });
    const { unmount } = renderPage();
    expect(await screen.findByText(/no weak topics detected/i)).toBeInTheDocument();
    unmount();
    mockGetRevisionPlan.mockClear(); // count only calls made by the second render below

    mockGetRevisionPlan.mockResolvedValueOnce({
      data: {
        plan: {
          track: "NEET",
          generated_at: "2026-09-27T15:30:00Z",
          items: [
            { subject: "Biology", topic: "Cell", mastery: 20, attempts: 1, priority: "high" },
            { subject: "Biology", topic: "Anatomy", mastery: 40, attempts: 1, priority: "medium" },
          ],
        },
      },
    });
    renderPage();
    expect(await screen.findByText(/Cell/)).toBeInTheDocument();
    expect(screen.getByText(/Anatomy/)).toBeInTheDocument();
    expect(screen.queryByText(/no weak topics detected/i)).not.toBeInTheDocument();
    expect(mockGetRevisionPlan).toHaveBeenCalledTimes(1);
  });
});
