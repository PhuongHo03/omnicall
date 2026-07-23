import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JsonValue } from "../components/JsonValue";

describe("JsonValue", () => {
  it("gives structured nested values a full-width row", () => {
    render(
      <JsonValue
        depth={0}
        value={{
          data: {
            subject: {
              type: "meeting",
              predicate: "has_reliable_speaker_count",
            },
          },
        }}
      />,
    );

    const dataLabel = screen.getByText("Data");
    const subjectLabel = screen.getByText("Subject");
    const typeValue = screen.getByText("meeting");

    expect(dataLabel.closest(".json-map__row")).toHaveClass("json-map__row--structured");
    expect(subjectLabel.closest(".json-map__row")).toHaveClass("json-map__row--structured");
    expect(typeValue.closest(".json-map__row")).not.toHaveClass("json-map__row--structured");
  });

  it("keeps arrays of primitive tags on the compact row", () => {
    render(<JsonValue depth={0} value={{ citationIds: ["cite-025", "cite-038"] }} />);

    expect(screen.getByText("Citation Ids").closest(".json-map__row")).not.toHaveClass("json-map__row--structured");
    expect(screen.getByText("cite-038")).toBeInTheDocument();
  });
});
