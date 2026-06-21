import "react";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "docling-img": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string | object;
          items?: string;
          pagenumbers?: boolean;
          trim?: string;
          backdrop?: boolean;
        },
        HTMLElement
      >;
      "docling-tooltip": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
      "docling-overlay": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          items?: string;
        },
        HTMLElement
      >;
      "docling-table": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string | object;
        },
        HTMLElement
      >;
      "docling-picture-classification": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      >;
      "docling-picture-description": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      >;
    }
  }
}
