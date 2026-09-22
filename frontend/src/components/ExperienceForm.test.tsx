import { describe, expect, it } from "vitest";

import { toExperienceRequestBody, type ExperienceFormValues } from "./ExperienceForm";

function baseValues(overrides: Partial<ExperienceFormValues> = {}): ExperienceFormValues {
  return {
    position: "Engineer",
    company: "Acme",
    companyUrl: "",
    period: "2020-2022",
    location: "Remote",
    isGap: false,
    responsibilities: [],
    achievements: [],
    projects: [],
    ...overrides,
  };
}

describe("toExperienceRequestBody", () => {
  it("puts role-level (projectId: null) bullets straight into responsibilities/achievements", () => {
    const values = baseValues({
      achievements: [{ id: "b1", text: "Shipped v1", projectId: null }],
      responsibilities: [{ id: "b2", text: "Owned the backend", projectId: null }],
    });

    const body = toExperienceRequestBody(values);

    expect(body.achievements).toEqual(["Shipped v1"]);
    expect(body.responsibilities).toEqual(["Owned the backend"]);
    expect(body.projects).toEqual([]);
  });

  it("groups bullets tagged to a project under that project's own nested achievements/responsibilities", () => {
    const values = baseValues({
      achievements: [
        { id: "b1", text: "Role-level win", projectId: null },
        { id: "b2", text: "Shipped v1", projectId: "proj-1" },
        { id: "b3", text: "Shipped v2", projectId: "proj-1" },
      ],
      responsibilities: [{ id: "b4", text: "Owned deploys", projectId: "proj-1" }],
      projects: [{ id: "proj-1", name: "Internal tool", period: "2021", url: "" }],
    });

    const body = toExperienceRequestBody(values);

    expect(body.achievements).toEqual(["Role-level win"]);
    expect(body.projects).toEqual([
      {
        id: "proj-1",
        name: "Internal tool",
        period: "2021",
        achievements: ["Shipped v1", "Shipped v2"],
        responsibilities: ["Owned deploys"],
        url: null,
      },
    ]);
  });

  it("drops blank/whitespace-only bullet rows, mirroring the old BulletListEditor's trim-and-drop convention", () => {
    const values = baseValues({
      achievements: [
        { id: "b1", text: "Real one", projectId: null },
        { id: "b2", text: "   ", projectId: null },
        { id: "b3", text: "", projectId: null },
      ],
    });

    const body = toExperienceRequestBody(values);

    expect(body.achievements).toEqual(["Real one"]);
  });

  it("a project with a blank name is dropped, and its bullets fall back to role-level rather than being lost", () => {
    const values = baseValues({
      achievements: [{ id: "b1", text: "Orphaned achievement", projectId: "proj-1" }],
      projects: [{ id: "proj-1", name: "   ", period: "", url: "" }],
    });

    const body = toExperienceRequestBody(values);

    expect(body.projects).toEqual([]);
    expect(body.achievements).toEqual(["Orphaned achievement"]);
  });

  it("trims text fields and converts blank optional fields to null", () => {
    const values = baseValues({
      company: "  Acme  ",
      period: "  2020-2022  ",
      location: "   ",
      companyUrl: "  https://acme.example/  ",
      projects: [{ id: "proj-1", name: "Internal tool", period: "  ", url: "  https://proj.example/  " }],
    });

    const body = toExperienceRequestBody(values);

    expect(body.company).toBe("Acme");
    expect(body.company_url).toBe("https://acme.example/");
    expect(body.period).toBe("2020-2022");
    expect(body.location).toBeNull();
    expect(body.projects[0].period).toBeNull();
    expect(body.projects[0].url).toBe("https://proj.example/");
  });
});
