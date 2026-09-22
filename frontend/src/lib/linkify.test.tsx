import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LINK_CLASSNAME, Linkify, linkifyContactLine, linkifyText } from "./linkify";

describe("linkifyText", () => {
  it("turns a bare email address into a mailto: link", () => {
    render(<p data-testid="p">{linkifyText("Email: dns20.01.88@gmail.com")}</p>);

    const link = screen.getByRole("link", { name: "dns20.01.88@gmail.com" });
    expect(link).toHaveAttribute("href", "mailto:dns20.01.88@gmail.com");
    expect(screen.getByTestId("p")).toHaveTextContent("Email: dns20.01.88@gmail.com");
  });

  it("turns an https:// URL into a link with its own href, unmodified", () => {
    render(<p>{linkifyText("Portfolio: https://example.com/anton")}</p>);

    const link = screen.getByRole("link", { name: "https://example.com/anton" });
    expect(link).toHaveAttribute("href", "https://example.com/anton");
  });

  it("turns a bare www. URL into a link, prefixed with https:// for its href", () => {
    render(<p>{linkifyText("LinkedIn: www.linkedin.com/in/anton")}</p>);

    const link = screen.getByRole("link", { name: "www.linkedin.com/in/anton" });
    expect(link).toHaveAttribute("href", "https://www.linkedin.com/in/anton");
  });

  it("strips trailing sentence punctuation from a URL but keeps it as plain text after", () => {
    render(<p data-testid="p">{linkifyText("(see https://example.com/x).")}</p>);

    expect(screen.getByRole("link", { name: "https://example.com/x" })).toBeInTheDocument();
    // The full paragraph text is unchanged — only the URL substring
    // itself became a link, the surrounding "(see " / ")." stayed plain.
    expect(screen.getByTestId("p")).toHaveTextContent("(see https://example.com/x).");
  });

  it("links open in a new tab safely", () => {
    render(<p>{linkifyText("https://example.com")}</p>);

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("gives the link a visible style — found live: a bare <a> with no classes was indistinguishable from surrounding text once Tailwind's Preflight reset stripped the browser's own default blue/underline", () => {
    render(<p>{linkifyText("https://example.com")}</p>);

    expect(screen.getByRole("link")).toHaveClass(...LINK_CLASSNAME.split(" "));
  });

  it("joins multiple contacts, linking only the email/URL substrings", () => {
    render(
      <p data-testid="p">
        {linkifyText("Email: a@b.com | Phone: +1 555 0100 | Portfolio: https://a.dev")}
      </p>,
    );

    expect(screen.getByRole("link", { name: "a@b.com" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://a.dev" })).toBeInTheDocument();
    expect(screen.getByTestId("p")).toHaveTextContent(
      "Email: a@b.com | Phone: +1 555 0100 | Portfolio: https://a.dev",
    );
  });

  it("leaves plain text with no email or URL completely untouched", () => {
    render(<p>{linkifyText("Roadmapping; Team Management")}</p>);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Roadmapping; Team Management")).toBeInTheDocument();
  });

  it("Linkify component renders the same as calling linkifyText directly", () => {
    render(<Linkify text="Email: a@b.com" />);

    expect(screen.getByRole("link", { name: "a@b.com" })).toHaveAttribute("href", "mailto:a@b.com");
  });

  it("leaves a bare domain inside free text unlinked — that's linkifyContactLine's job, not this one's", () => {
    // Regression guard for the false positive a general bare-domain scan
    // would cause: "ASP.NET"/"Node.js" are real technology names, not
    // links, and linkifyText must never touch them.
    render(<p>{linkifyText("ASP.NET; Node.js; linkedin.com/in/anton")}</p>);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("linkifyContactLine", () => {
  it("turns a bare-domain LinkedIn value (no http/www prefix) into a link — a real resume's own format", () => {
    render(<p>{linkifyContactLine("LinkedIn", "linkedin.com/in/anton-guzeev")}</p>);

    const link = screen.getByRole("link", { name: "linkedin.com/in/anton-guzeev" });
    expect(link).toHaveAttribute("href", "https://linkedin.com/in/anton-guzeev");
    expect(link).toHaveClass(...LINK_CLASSNAME.split(" "));
  });

  it("turns a bare-domain portfolio subdomain value into a link", () => {
    render(<p>{linkifyContactLine("Portfolio", "aguzeev.artstation.com")}</p>);

    const link = screen.getByRole("link", { name: "aguzeev.artstation.com" });
    expect(link).toHaveAttribute("href", "https://aguzeev.artstation.com");
  });

  it("still turns an email value into a mailto: link", () => {
    render(<p>{linkifyContactLine("Email", "anton@example.com")}</p>);

    expect(screen.getByRole("link", { name: "anton@example.com" })).toHaveAttribute(
      "href",
      "mailto:anton@example.com",
    );
  });

  it("leaves a non-link value (phone, location, free-text work authorization) as plain text", () => {
    render(<p data-testid="p">{linkifyContactLine("Phone", "+49 1522 6475201")}</p>);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByTestId("p")).toHaveTextContent("Phone: +49 1522 6475201");

    const { getByTestId } = render(
      <p data-testid="p2">
        {linkifyContactLine(
          "Work Authorization",
          "Permanent Residency Visa in Germany – no visa sponsorship needed.",
        )}
      </p>,
    );
    expect(getByTestId("p2")).toHaveTextContent(
      "Work Authorization: Permanent Residency Visa in Germany – no visa sponsorship needed.",
    );
  });

});
