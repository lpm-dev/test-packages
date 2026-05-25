import { styled } from "@/styled-system/jsx"
import { tokens } from "@/components/lib/tokens"

export const StyledButton = styled("button", {
  base: {
    fontWeight: "600",
    borderRadius: "md",
    cursor: "pointer",
    transition: "all 0.2s",
  },
  variants: {
    variant: {
      solid: {
        backgroundColor: tokens.primary,
        color: "white",
      },
      outline: {
        backgroundColor: "transparent",
        borderWidth: "1px",
        borderColor: tokens.primary,
        color: tokens.primary,
      },
    },
    size: {
      sm: { px: "3", py: "1.5", fontSize: "sm" },
      md: { px: "4", py: "2", fontSize: "md" },
      lg: { px: "6", py: "3", fontSize: "lg" },
    },
  },
  defaultVariants: {
    variant: "solid",
    size: "md",
  },
})
