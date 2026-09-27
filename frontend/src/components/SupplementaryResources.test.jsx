import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import SupplementaryResources from "./SupplementaryResources";

const VIDEO = {
  title: "Cell Structure Explained",
  url: "https://www.youtube.com/watch?v=cell1",
  description: "A walkthrough of cell structure.",
  resource_type: "VIDEO",
  source: "youtube.com",
};
const ARTICLE = {
  title: "Understanding Normalization",
  url: "https://example.edu/normalization",
  description: "University reference page.",
  resource_type: "ARTICLE",
  source: "example.edu",
};
const REAL_WORLD = {
  title: "Fraud Detection with Classification",
  url: "https://example.com/fraud-detection",
  description: "How banks flag fraud using ML.",
  resource_type: "REAL_WORLD_EXAMPLE",
  source: "example.com",
};

describe("SupplementaryResources", () => {
  it("renders nothing when resources is null/undefined", () => {
    const { container: c1 } = render(<SupplementaryResources resources={null} />);
    expect(c1).toBeEmptyDOMElement();
    const { container: c2 } = render(<SupplementaryResources resources={undefined} />);
    expect(c2).toBeEmptyDOMElement();
  });

  it("hides the entire section when all three lists are empty", () => {
    const { container } = render(
      <SupplementaryResources resources={{ videos: [], articles: [], real_world_examples: [] }} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders videos correctly with a real external link", () => {
    render(<SupplementaryResources resources={{ videos: [VIDEO], articles: [], real_world_examples: [] }} />);
    expect(screen.getByText(/Videos/)).toBeInTheDocument();
    expect(screen.getByText("Cell Structure Explained")).toBeInTheDocument();
    expect(screen.getByText("A walkthrough of cell structure.")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Watch/i });
    expect(link).toHaveAttribute("href", VIDEO.url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders articles correctly", () => {
    render(<SupplementaryResources resources={{ videos: [], articles: [ARTICLE], real_world_examples: [] }} />);
    expect(screen.getByText(/Articles/)).toBeInTheDocument();
    expect(screen.getByText("Understanding Normalization")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Read/i });
    expect(link).toHaveAttribute("href", ARTICLE.url);
  });

  it("renders real-world examples correctly", () => {
    render(<SupplementaryResources resources={{ videos: [], articles: [], real_world_examples: [REAL_WORLD] }} />);
    expect(screen.getByText(/Real-World Examples/)).toBeInTheDocument();
    expect(screen.getByText("Fraud Detection with Classification")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Explore/i });
    expect(link).toHaveAttribute("href", REAL_WORLD.url);
  });

  it("renders all three categories together without mixing them up", () => {
    render(<SupplementaryResources resources={{ videos: [VIDEO], articles: [ARTICLE], real_world_examples: [REAL_WORLD] }} />);
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(screen.getByRole("link", { name: /Watch/i })).toHaveAttribute("href", VIDEO.url);
    expect(screen.getByRole("link", { name: /Read/i })).toHaveAttribute("href", ARTICLE.url);
    expect(screen.getByRole("link", { name: /Explore/i })).toHaveAttribute("href", REAL_WORLD.url);
  });

  it("only shows sections that actually have items", () => {
    render(<SupplementaryResources resources={{ videos: [VIDEO], articles: [], real_world_examples: [] }} />);
    expect(screen.queryByText(/^Articles$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Real-World Examples/)).not.toBeInTheDocument();
  });
});
