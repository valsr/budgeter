import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Category } from "../api/types";
import { CategoryCombobox } from "./CategoryCombobox";

const resolvePath = vi.fn();
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { resolvePath: (...args: unknown[]) => resolvePath(...args) },
}));

const categories: Category[] = [
  {
    id: 1,
    name: "shared",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null, is_income: false,
    children: [
      { id: 2, name: "groceries", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, is_income: false, children: [] },
      { id: 3, name: "utilities", parent_id: 1, color: "#333", sort_order: 1, archived_at: null, is_income: false, children: [] },
    ],
  },
];

describe("CategoryCombobox", () => {
  beforeEach(() => {
    resolvePath.mockReset();
  });

  it("shows the current selection's path", () => {
    render(<CategoryCombobox categories={categories} value={2} onChange={() => {}} />);
    expect(screen.getByDisplayValue("shared:groceries")).toBeInTheDocument();
  });

  it("filters options as you type and selects one by clicking", () => {
    const onChange = vi.fn();
    render(<CategoryCombobox categories={categories} value={null} onChange={onChange} />);
    const input = screen.getByPlaceholderText("Type to search or create…");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "util" } });

    expect(screen.getByText("shared:utilities")).toBeInTheDocument();
    expect(screen.queryByText("shared:groceries")).not.toBeInTheDocument();

    fireEvent.mouseDown(screen.getByText("shared:utilities"));
    expect(onChange).toHaveBeenCalledWith(3);
    expect(input).toHaveValue("shared:utilities");
  });

  it("offers to create a category for a path with no match, in assign mode", async () => {
    resolvePath.mockResolvedValue({ id: 99, name: "alcohol", parent_id: 2 });
    const onChange = vi.fn();
    const onCreated = vi.fn();
    render(<CategoryCombobox categories={categories} value={null} onChange={onChange} onCreated={onCreated} />);
    const input = screen.getByPlaceholderText("Type to search or create…");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "shared:groceries:alcohol" } });

    const createRow = screen.getByText('+ Create "shared:groceries:alcohol"');
    fireEvent.mouseDown(createRow);

    await vi.waitFor(() => expect(resolvePath).toHaveBeenCalledWith("shared:groceries:alcohol"));
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(99));
    expect(onCreated).toHaveBeenCalled();
  });

  it("does not offer to create in filter mode", () => {
    render(<CategoryCombobox categories={categories} value={null} onChange={() => {}} mode="filter" />);
    const input = screen.getByPlaceholderText("Search categories…");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "nonexistent" } });

    expect(screen.queryByText(/Create/)).not.toBeInTheDocument();
    expect(screen.getByText("No matches")).toBeInTheDocument();
  });

  it("does not offer to create when the typed path exactly matches an existing category", () => {
    render(<CategoryCombobox categories={categories} value={null} onChange={() => {}} />);
    const input = screen.getByPlaceholderText("Type to search or create…");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "shared:groceries" } });

    expect(screen.queryByText(/Create/)).not.toBeInTheDocument();
  });

  it("shows a clear row (e.g. Unassigned) only when the query is empty", () => {
    render(<CategoryCombobox categories={categories} value={2} onChange={() => {}} clearLabel="Unassigned" />);
    const input = screen.getByDisplayValue("shared:groceries");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByText("Unassigned")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "x" } });
    expect(screen.queryByText("Unassigned")).not.toBeInTheDocument();
  });

  it("selecting the clear row commits null", () => {
    const onChange = vi.fn();
    render(<CategoryCombobox categories={categories} value={2} onChange={onChange} clearLabel="Unassigned" />);
    const input = screen.getByDisplayValue("shared:groceries");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.mouseDown(screen.getByText("Unassigned"));

    expect(onChange).toHaveBeenCalledWith(null);
    expect(input).toHaveValue("");
  });

  it("Escape reverts unsaved typing back to the current selection", () => {
    render(<CategoryCombobox categories={categories} value={2} onChange={() => {}} />);
    const input = screen.getByDisplayValue("shared:groceries");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "garbage" } });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(input).toHaveValue("shared:groceries");
  });

  it("blurring without an explicit selection reverts to the current value", () => {
    render(<CategoryCombobox categories={categories} value={2} onChange={() => {}} />);
    const input = screen.getByDisplayValue("shared:groceries");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "garbage" } });
    fireEvent.blur(input);

    expect(input).toHaveValue("shared:groceries");
  });

  it("Enter selects the highlighted option", () => {
    const onChange = vi.fn();
    render(<CategoryCombobox categories={categories} value={null} onChange={onChange} />);
    const input = screen.getByPlaceholderText("Type to search or create…");

    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "util" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith(3);
  });
});
