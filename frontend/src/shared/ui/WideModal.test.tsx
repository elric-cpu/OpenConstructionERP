// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for WideModal — the shared modal used by Service, Procurement,
// BI Dashboards, HSE Advanced and other module pages whose create/edit
// forms have many fields. Behaviour covered:
//   1. Renders nothing when open=false.
//   2. Renders title, subtitle, body and sticky footer when open=true.
//   3. Escape closes the dialog (unless busy=true).
//   4. Backdrop click closes the dialog (unless busy=true).
//   5. Click inside the panel does not close.
//   6. Body scroll is locked while open and restored when closed.
//   7. WideModalField renders required marker, hint, and error text.
//   8. WideModalSection lays out children in a responsive grid.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { WideModal, WideModalSection, WideModalField } from './WideModal';

beforeEach(() => {
  document.body.style.overflow = '';
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.style.overflow = '';
});

function renderModal(props: Partial<React.ComponentProps<typeof WideModal>> = {}) {
  const onClose = vi.fn();
  const utils = render(
    <WideModal
      open={props.open ?? true}
      onClose={onClose}
      title={props.title ?? 'Test modal'}
      subtitle={props.subtitle}
      busy={props.busy}
      size={props.size}
      footer={props.footer}
    >
      {props.children ?? <div data-testid="modal-body">body content</div>}
    </WideModal>,
  );
  return { onClose, ...utils };
}

describe('WideModal', () => {
  it('renders nothing when open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders title, subtitle and body when open=true', () => {
    renderModal({
      subtitle: 'Optional descriptive subtitle for the form.',
    });
    expect(screen.getByRole('dialog', { name: /Test modal/i })).toBeInTheDocument();
    expect(
      screen.getByText('Optional descriptive subtitle for the form.'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('modal-body')).toBeInTheDocument();
  });

  it('renders the sticky footer when supplied', () => {
    renderModal({
      footer: <button>Save</button>,
    });
    expect(screen.getByRole('button', { name: /Save/ })).toBeInTheDocument();
  });

  it('Escape closes the modal', () => {
    const { onClose } = renderModal();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('Escape does NOT close when busy=true', () => {
    const { onClose } = renderModal({ busy: true });
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('clicking the backdrop closes; clicking the panel does not', () => {
    const { onClose } = renderModal();
    // Click on the backdrop (the dialog root)
    const dialog = screen.getByRole('dialog');
    fireEvent.mouseDown(dialog);
    expect(onClose).toHaveBeenCalled();

    // Reset and click on the inner body — should NOT close
    onClose.mockClear();
    const body = screen.getByTestId('modal-body');
    fireEvent.mouseDown(body);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('locks body scroll while open and restores it on unmount', () => {
    document.body.style.overflow = '';
    const { unmount } = render(
      <WideModal open onClose={() => undefined} title="Scroll test">
        <p>content</p>
      </WideModal>,
    );
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(document.body.style.overflow).toBe('');
  });
});

describe('WideModalField', () => {
  it('shows the required asterisk when required=true', () => {
    render(
      <WideModalField label="Customer" required>
        <input data-testid="f" />
      </WideModalField>,
    );
    // The * is rendered next to the label text with text-semantic-error
    expect(screen.getByText(/Customer/)).toBeInTheDocument();
    expect(screen.getByText('*')).toBeInTheDocument();
  });

  it('renders hint text when provided and no error', () => {
    render(
      <WideModalField label="Email" hint="We will never share your email.">
        <input data-testid="f" />
      </WideModalField>,
    );
    expect(
      screen.getByText('We will never share your email.'),
    ).toBeInTheDocument();
  });

  it('renders error text when provided (overrides hint)', () => {
    render(
      <WideModalField
        label="Email"
        hint="Hint that should not appear"
        error="Invalid email address"
      >
        <input data-testid="f" />
      </WideModalField>,
    );
    expect(screen.getByText('Invalid email address')).toBeInTheDocument();
    expect(
      screen.queryByText('Hint that should not appear'),
    ).toBeNull();
  });

  it('propagates aria-required to the inner control when required=true (WCAG 3.3.2)', () => {
    render(
      <WideModalField label="Email" required>
        <input data-testid="email-field" />
      </WideModalField>,
    );
    const input = screen.getByTestId('email-field');
    expect(input).toHaveAttribute('aria-required', 'true');
  });

  it('does NOT add aria-required when required=false', () => {
    render(
      <WideModalField label="Phone">
        <input data-testid="phone-field" />
      </WideModalField>,
    );
    const input = screen.getByTestId('phone-field');
    expect(input).not.toHaveAttribute('aria-required');
  });

  it('respects an aria-required already declared by the caller', () => {
    render(
      <WideModalField label="Notes" required>
        <textarea data-testid="notes" aria-required="false" />
      </WideModalField>,
    );
    // Caller's explicit value wins — we do not overwrite.
    expect(screen.getByTestId('notes')).toHaveAttribute(
      'aria-required',
      'false',
    );
  });
});

describe('WideModalSection', () => {
  it('renders the section heading and description', () => {
    render(
      <WideModalSection
        title="Customer details"
        description="Pick from your contacts."
      >
        <input />
      </WideModalSection>,
    );
    expect(screen.getByRole('heading', { name: 'Customer details' }))
      .toBeInTheDocument();
    expect(screen.getByText('Pick from your contacts.')).toBeInTheDocument();
  });
});
