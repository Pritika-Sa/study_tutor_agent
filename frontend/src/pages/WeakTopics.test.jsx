import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import WeakTopics from "./WeakTopics";

const mockUseTrack = vi.fn();
vi.mock("../context/TrackContext", () => ({
  useTrack: () => mockUseTrack(),
}));

const mockGetWeakTopics = vi.fn();
const mockGetProgress = vi.fn();
vi.mock("../api/progressApi", () => ({
  getWeakTopics: (...args) => mockGetWeakTopics(...args),
  getProgress: (...args) => mockGetProgress(...args),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <WeakTopics />
    </MemoryRouter>
  );
}

describe("WeakTopics", () => {
  it("does not crash on the initial render before the fetch resolves (loading=false, weakTopics=null)", () => {
    // Reproduces the reported bug: a track is already selected (persisted
    // from a prior session), so on mount -- before useEffect has had a
    // chance to call setLoading(true) -- the component must not try to
    // read .length off state that is still null.
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetWeakTopics.mockReturnValue(new Promise(() => {})); // never resolves during this test
    mockGetProgress.mockReturnValue(new Promise(() => {}));
    expect(() => renderPage()).not.toThrow();
  });

  it("shows the empty state instead of a blank page when there are no weak topics", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetWeakTopics.mockResolvedValue({ data: { weak_topics: [] } });
    mockGetProgress.mockResolvedValue({ data: { strong_topics: [] } });
    renderPage();
    expect(await screen.findByText(/no weak topics have been identified yet/i)).toBeInTheDocument();
  });

  it("renders real weak topics from the backend response", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetWeakTopics.mockResolvedValue({
      data: { weak_topics: [{ subject: "Biology", topic: "Cell Structure", mastery: 42, attempts: 3 }] },
    });
    mockGetProgress.mockResolvedValue({ data: { strong_topics: [] } });
    renderPage();
    expect(await screen.findByText("Biology")).toBeInTheDocument();
    expect(screen.getByText("Cell Structure")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows a retry-able error message instead of crashing when the API call fails", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET" });
    mockGetWeakTopics.mockRejectedValue(new Error("network down"));
    mockGetProgress.mockResolvedValue({ data: { strong_topics: [] } });
    renderPage();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("prompts for a track instead of crashing when none is selected", () => {
    mockUseTrack.mockReturnValue({ track: null });
    renderPage();
    expect(screen.getByText(/select a track/i)).toBeInTheDocument();
  });
});
