import { ComponentPropsWithoutRef, ReactNode } from "react"

export interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
	children?: ReactNode
	variant?: "solid" | "outline"
	size?: "sm" | "md" | "lg"
}

export default function Button(props: ButtonProps): JSX.Element
