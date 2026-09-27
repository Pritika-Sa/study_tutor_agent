import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Tutor from "./Tutor";

const mockUseTrack = vi.fn();
vi.mock("../context/TrackContext", () => ({
  useTrack: () => mockUseTrack(),
}));

const mockAskTutor = vi.fn();
vi.mock("../api/tutorApi", () => ({
  askTutor: (...args) => mockAskTutor(...args),
}));

async function askQuestion(question = "What is database normalization?") {
  fireEvent.change(screen.getByPlaceholderText(/e\.g\. explain database normalization/i), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.queryByText(/thinking/i)).not.toBeInTheDocument());
}

describe("Tutor", () => {
  it("prompts to select a track/subject before asking anything", () => {
    mockUseTrack.mockReturnValue({ track: null, subject: null });
    render(<Tutor />);
    expect(screen.getByText(/select a track and subject/i)).toBeInTheDocument();
  });

  it("renders the grounded answer and KB citations when supplementary resources are unavailable (Tavily failure)", async () => {
    // Mirrors the backend's own graceful-degradation contract: Tavily
    // failing (missing key, network error, etc.) never breaks the answer --
    // supplementary_resources just comes back empty. The main answer and
    // citations must render exactly as if Tavily had never been involved.
    mockUseTrack.mockReturnValue({ track: "Placement", subject: "DBMS" });
    mockAskTutor.mockResolvedValue({
      data: {
        answer: "Normalization reduces data redundancy.",
        topic: null,
        citations: [{ source: "OTHER", subject: "DBMS", document_name: "notes.pdf", page: 3 }],
        web_citations: [],
        source_type: "KB",
        supplementary_resources: { videos: [], articles: [], real_world_examples: [] },
      },
    });

    render(<Tutor />);
    await askQuestion();

    expect(screen.getByText("Normalization reduces data redundancy.")).toBeInTheDocument();
    expect(screen.getByText(/OTHER/)).toBeInTheDocument();
    // No supplementary section should render at all.
    expect(screen.queryByText(/Explore More/i)).not.toBeInTheDocument();
  });

  it("still renders the answer when supplementary_resources is missing from the response entirely", async () => {
    mockUseTrack.mockReturnValue({ track: "Placement", subject: "DBMS" });
    mockAskTutor.mockResolvedValue({
      data: {
        answer: "Normalization reduces data redundancy.",
        topic: null,
        citations: [],
        web_citations: [],
        source_type: "KB",
        // supplementary_resources intentionally omitted -- an older backend shape.
      },
    });

    render(<Tutor />);
    await askQuestion();

    expect(screen.getByText("Normalization reduces data redundancy.")).toBeInTheDocument();
    expect(screen.queryByText(/Explore More/i)).not.toBeInTheDocument();
  });

  it("renders supplementary resources alongside the answer when available", async () => {
    mockUseTrack.mockReturnValue({ track: "NEET", subject: "Biology" });
    mockAskTutor.mockResolvedValue({
      data: {
        answer: "The mitochondria is the powerhouse of the cell.",
        topic: "Cell",
        citations: [{ source: "NCERT", subject: "Biology", document_name: "kebo108.pdf", page: 13 }],
        web_citations: [],
        source_type: "KB",
        supplementary_resources: {
          videos: [{ title: "Mitochondria Explained", url: "https://www.youtube.com/watch?v=abc", description: "Video.", source: "youtube.com" }],
          articles: [],
          real_world_examples: [],
        },
      },
    });

    render(<Tutor />);
    await askQuestion("What is the function of mitochondria?");

    expect(screen.getByText("The mitochondria is the powerhouse of the cell.")).toBeInTheDocument();
    expect(screen.getByText(/Explore More/i)).toBeInTheDocument();
    expect(screen.getByText("Mitochondria Explained")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Watch/i })).toHaveAttribute(
      "href",
      "https://www.youtube.com/watch?v=abc"
    );
  });

  it("shows a retry-able error and does not crash the page when the whole request fails", async () => {
    mockUseTrack.mockReturnValue({ track: "Placement", subject: "DBMS" });
    mockAskTutor.mockRejectedValue(new Error("network down"));

    render(<Tutor />);
    await askQuestion();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
