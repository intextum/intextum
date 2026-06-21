import { GripVertical } from "lucide-react";
import type * as React from "react";
import * as ResizablePrimitive from "react-resizable-panels";
import type { GroupProps, Orientation } from "react-resizable-panels";

import { cn } from "@/lib/utils";

const ResizablePanelGroup = ({
  className,
  direction,
  resizeTargetMinimumSize,
  ...props
}: Omit<GroupProps, "orientation"> & { direction?: Orientation }) => (
  <ResizablePrimitive.Group
    className={cn("flex h-full w-full data-[panel-group-direction=vertical]:flex-col", className)}
    orientation={direction}
    resizeTargetMinimumSize={resizeTargetMinimumSize ?? { fine: 4, coarse: 24 }}
    {...props}
  />
);

const ResizablePanel = ResizablePrimitive.Panel;

const ResizableHandle = ({
  withHandle,
  className,
  onClickCapture,
  onMouseDownCapture,
  onPointerDownCapture,
  onTouchStartCapture,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Separator> & {
  withHandle?: boolean;
}) => {
  const stopDialogOutsideClick = (event: React.SyntheticEvent<HTMLDivElement>) => {
    event.stopPropagation();
  };

  return (
    <ResizablePrimitive.Separator
      className={cn(
        "relative flex w-px items-center justify-center bg-border after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 focus-visible:outline-hidden focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-1 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:translate-x-0 data-[panel-group-direction=vertical]:after:-translate-y-1/2 [&[data-panel-group-direction=vertical]>div]:rotate-90",
        className,
      )}
      onClickCapture={(event) => {
        stopDialogOutsideClick(event);
        onClickCapture?.(event);
      }}
      onMouseDownCapture={(event) => {
        stopDialogOutsideClick(event);
        onMouseDownCapture?.(event);
      }}
      onPointerDownCapture={(event) => {
        stopDialogOutsideClick(event);
        onPointerDownCapture?.(event);
      }}
      onTouchStartCapture={(event) => {
        stopDialogOutsideClick(event);
        onTouchStartCapture?.(event);
      }}
      data-dialog-resize-handle=""
      {...props}
    >
      {withHandle && (
        <div
          className="z-10 flex h-4 w-3 items-center justify-center rounded-sm border bg-border"
          data-dialog-resize-handle=""
        >
          <GripVertical className="h-2.5 w-2.5" />
        </div>
      )}
    </ResizablePrimitive.Separator>
  );
};

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
