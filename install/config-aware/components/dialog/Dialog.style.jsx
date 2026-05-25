import { styled } from "@/styled-system/jsx"
import { tokens } from "@/components/lib/tokens"

export const Overlay = styled("div", {
  base: {
    position: "fixed",
    inset: "0",
    backgroundColor: "rgba(0, 0, 0, 0.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: "50",
  },
})

export const DialogPanel = styled("div", {
  base: {
    backgroundColor: "white",
    borderRadius: "lg",
    padding: "6",
    maxWidth: "md",
    width: "100%",
    boxShadow: "xl",
  },
})

export const DialogTitle = styled("h2", {
  base: {
    fontSize: "lg",
    fontWeight: "600",
    color: tokens.primary,
    marginBottom: "4",
  },
})
