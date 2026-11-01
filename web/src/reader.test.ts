import { describe, expect, it } from "vitest";
import { whereToRead } from "./reader";

const paper = { id: "W1", doi: null, open_access_url: null, pdf_url: null, short: "Sghaier, 2022", title: "Drought" };

describe("where a cited page is read", () => {
  it("opens the researcher's own file inside Magonia, at the page", () => {
    expect(whereToRead({ ...paper, id: "U3", title: "Field notes" }, 6)).toEqual({
      title: "Field notes",
      url: "/api/library/U3/pdf#page=6",
      inside: true,
    });
  });

  it("opens an open-access PDF at the page, else the publisher's page", () => {
    expect(whereToRead({ ...paper, pdf_url: "https://x.org/a.pdf", doi: "10.1/x" }, 2)?.url).toBe("https://x.org/a.pdf#page=2");
    expect(whereToRead({ ...paper, doi: "10.1/x" }, 2)?.url).toBe("https://doi.org/10.1/x");
    expect(whereToRead(paper)).toBeNull();
  });
});
