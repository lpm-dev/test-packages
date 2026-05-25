import { Overlay, DialogPanel, DialogTitle } from "@/components/dialog/Dialog.style"

export default function Dialog({ open, onClose, title, children }) {
  if (!open) return null

  return (
    <Overlay onClick={onClose}>
      <DialogPanel onClick={(e) => e.stopPropagation()}>
        {title && <DialogTitle>{title}</DialogTitle>}
        {children}
      </DialogPanel>
    </Overlay>
  )
}
