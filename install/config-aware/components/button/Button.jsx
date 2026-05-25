import { StyledButton } from "@/components/button/Button.style"

export default function Button({ children, variant = "solid", size = "md", ...props }) {
  return (
    <StyledButton variant={variant} size={size} {...props}>
      {children}
    </StyledButton>
  )
}
