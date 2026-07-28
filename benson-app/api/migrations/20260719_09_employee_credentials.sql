ALTER TABLE identity_provisioning_commands
    DROP CONSTRAINT IF EXISTS ck_identity_command_status;

ALTER TABLE identity_provisioning_commands
    ADD CONSTRAINT ck_identity_command_status CHECK (
        status IN (
            'pending_approval', 'manual_setup_required', 'approved',
            'executing', 'verified', 'admin_confirmation_required',
            'admin_confirmed', 'failed', 'manual_review_required', 'suspended'
        )
    );

-- Rollback contract: remove manual_setup_required only after every command has
-- transitioned out of that state, then restore the prior check constraint.
