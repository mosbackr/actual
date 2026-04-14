"use client";

import { useCallback, useEffect, useRef } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function Modal({ open, onClose, title, children, actions }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (open) document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, handleKey]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-text-primary/30 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="bg-surface border border-border rounded p-6 w-full max-w-md mx-4 shadow-lg">
        <h3 className="text-sm font-medium text-text-primary mb-3">{title}</h3>
        <div className="text-sm text-text-secondary">{children}</div>
        {actions && <div className="flex justify-end gap-3 mt-5">{actions}</div>}
      </div>
    </div>
  );
}

/* Convenience wrappers */

interface AlertModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  message: string;
  variant?: "info" | "success" | "error";
}

const variantStyles = {
  info: "bg-accent/10 text-accent border-accent/20",
  success: "bg-score-high/10 text-score-high border-score-high/20",
  error: "bg-score-low/10 text-score-low border-score-low/20",
};

export function AlertModal({
  open,
  onClose,
  title = "Notice",
  message,
  variant = "info",
}: AlertModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      actions={
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
        >
          OK
        </button>
      }
    >
      <div className={`rounded border px-3 py-2 text-sm ${variantStyles[variant]}`}>
        {message}
      </div>
    </Modal>
  );
}

interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message: string;
  confirmLabel?: string;
  destructive?: boolean;
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title = "Confirm",
  message,
  confirmLabel = "Confirm",
  destructive = false,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      actions={
        <>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              onConfirm();
              onClose();
            }}
            className="px-4 py-2 text-sm font-medium rounded text-white transition bg-accent hover:bg-accent-hover"
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p>{message}</p>
    </Modal>
  );
}
