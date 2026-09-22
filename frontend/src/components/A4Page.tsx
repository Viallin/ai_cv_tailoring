import { forwardRef, type ReactNode } from "react";

import type { CvTemplate } from "@/lib/cvTemplates";

interface A4PageProps {
  template: CvTemplate;
  children: ReactNode;
}

// The visual "paper" container — fixed A4-proportioned width, template
// CSS custom properties applied inline (data-template is set for
// debugging/testing, the actual styling comes from the inline vars so a
// template swap doesn't require a matching CSS selector per template
// id). Single scrollable box on screen — real pagination only happens in
// the templated PDF export (Phase 16b/16c); Phase 29's PageBreakGuide
// draws dotted lines over this same continuous flow to show where those
// real breaks would land, without this component needing to know
// anything about that.
//
// Phase 29 — forwardRef so DocumentEditor.tsx can hand PageBreakGuide
// the page's own DOM node directly, the same "measure the real live DOM,
// don't recompute a parallel layout" approach DocumentGutter.tsx (Phase
// 28) already established; no internal state or behavior change here.
export const A4Page = forwardRef<HTMLDivElement, A4PageProps>(function A4Page({ template, children }, ref) {
  return (
    <div ref={ref} className="cv-a4-page" data-template={template.id} style={template.cssVars as React.CSSProperties}>
      {children}
    </div>
  );
});
