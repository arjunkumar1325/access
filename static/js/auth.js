/**
 * AccessAI — Authentication Client-side Controller (Login & Registration)
 * Handles client-side validation, password visibility toggles,
 * real-time strength evaluation, accessible modals, and form submission states.
 */

document.addEventListener('DOMContentLoaded', () => {
    initPasswordToggles();
    initLoginForm();
    initRegisterForm();
    initForgotPasswordModal();
});

/**
 * Initialize all show/hide password buttons
 */
function initPasswordToggles() {
    const toggleButtons = document.querySelectorAll('.btn-toggle-password');

    toggleButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (!input) return;

            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';

            btn.setAttribute('aria-pressed', isPassword ? 'true' : 'false');
            btn.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');

            const eyeIcon = btn.querySelector('.icon-eye');
            const eyeOffIcon = btn.querySelector('.icon-eye-off');
            if (eyeIcon && eyeOffIcon) {
                if (isPassword) {
                    eyeIcon.style.display = 'none';
                    eyeOffIcon.style.display = 'inline-block';
                } else {
                    eyeIcon.style.display = 'inline-block';
                    eyeOffIcon.style.display = 'none';
                }
            }

            input.focus();
        });
    });
}

/**
 * Validates email with standard compliant regex
 */
function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(String(email).toLowerCase());
}

/**
 * Shows inline error for an input field
 */
function setFieldError(inputId, errorId, message) {
    const input = document.getElementById(inputId);
    const errorEl = document.getElementById(errorId);
    if (!input || !errorEl) return;

    if (message) {
        input.setAttribute('aria-invalid', 'true');
        errorEl.textContent = message;
        errorEl.classList.add('active');
    } else {
        input.removeAttribute('aria-invalid');
        errorEl.textContent = '';
        errorEl.classList.remove('active');
    }
}

/**
 * Initialize Login Form Client Validation & Loading State
 */
function initLoginForm() {
    const form = document.getElementById('login-form');
    if (!form) return;

    const emailInput = document.getElementById('login-email');
    const passwordInput = document.getElementById('login-password');
    const submitBtn = document.getElementById('btn-login-submit');

    // Real-time cleanup on input
    emailInput?.addEventListener('input', () => {
        setFieldError('login-email', 'login-email-error', null);
    });
    passwordInput?.addEventListener('input', () => {
        setFieldError('login-password', 'login-password-error', null);
    });

    form.addEventListener('submit', (e) => {
        let isValid = true;
        const email = emailInput?.value.trim() || '';
        const password = passwordInput?.value || '';

        // Email validation
        if (!email) {
            setFieldError('login-email', 'login-email-error', 'Please enter your email address.');
            isValid = false;
        } else if (!isValidEmail(email)) {
            setFieldError('login-email', 'login-email-error', 'Please enter a valid email address (e.g., name@example.com).');
            isValid = false;
        } else {
            setFieldError('login-email', 'login-email-error', null);
        }

        // Password validation
        if (!password) {
            setFieldError('login-password', 'login-password-error', 'Please enter your password.');
            isValid = false;
        } else {
            setFieldError('login-password', 'login-password-error', null);
        }

        if (!isValid) {
            e.preventDefault();
            // Focus first error field
            const firstError = form.querySelector('[aria-invalid="true"]');
            firstError?.focus();
            return false;
        }

        // Enter loading state
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.classList.add('loading');
        }
        return true;
    });
}

/**
 * Initialize Registration Form Client Validation & Password Strength
 */
function initRegisterForm() {
    const form = document.getElementById('register-form');
    if (!form) return;

    const nameInput = document.getElementById('register-name');
    const emailInput = document.getElementById('register-email');
    const passwordInput = document.getElementById('register-password');
    const confirmInput = document.getElementById('register-confirm');
    const submitBtn = document.getElementById('btn-register-submit');
    const strengthWrapper = document.getElementById('password-strength-wrapper');
    const strengthText = document.getElementById('strength-text');

    // Real-time password strength evaluation
    passwordInput?.addEventListener('input', () => {
        setFieldError('register-password', 'register-password-error', null);
        const val = passwordInput.value;
        if (!val) {
            if (strengthWrapper) strengthWrapper.className = 'password-strength-wrapper';
            if (strengthText) strengthText.textContent = 'Password must be at least 8 characters';
            return;
        }

        let score = 0;
        if (val.length >= 8) score++;
        if (val.length >= 12) score++;
        if (/[a-z]/.test(val) && /[A-Z]/.test(val)) score++;
        if (/\d/.test(val)) score++;
        if (/[^A-Za-z0-9]/.test(val)) score++;

        if (strengthWrapper && strengthText) {
            if (val.length < 8) {
                strengthWrapper.className = 'password-strength-wrapper strength-weak';
                strengthText.textContent = 'Too short (minimum 8 characters required)';
            } else if (score <= 2) {
                strengthWrapper.className = 'password-strength-wrapper strength-weak';
                strengthText.textContent = 'Weak: Add uppercase, numbers, or symbols';
            } else if (score <= 4) {
                strengthWrapper.className = 'password-strength-wrapper strength-medium';
                strengthText.textContent = 'Moderate: Good password strength';
            } else {
                strengthWrapper.className = 'password-strength-wrapper strength-strong';
                strengthText.textContent = 'Strong: Excellent accessible password security';
            }
        }

        // Also check confirmation if user already typed in confirm input
        if (confirmInput?.value) {
            validatePasswordMatch();
        }
    });

    confirmInput?.addEventListener('input', () => {
        validatePasswordMatch();
    });

    nameInput?.addEventListener('input', () => {
        setFieldError('register-name', 'register-name-error', null);
    });

    emailInput?.addEventListener('input', () => {
        setFieldError('register-email', 'register-email-error', null);
    });

    function validatePasswordMatch() {
        const p1 = passwordInput?.value || '';
        const p2 = confirmInput?.value || '';
        if (p2 && p1 !== p2) {
            setFieldError('register-confirm', 'register-confirm-error', 'Passwords do not match. Please verify.');
            return false;
        } else {
            setFieldError('register-confirm', 'register-confirm-error', null);
            return true;
        }
    }

    form.addEventListener('submit', (e) => {
        let isValid = true;
        const name = nameInput?.value.trim() || '';
        const email = emailInput?.value.trim() || '';
        const password = passwordInput?.value || '';
        const confirm = confirmInput?.value || '';

        // Name validation
        if (!name || name.length < 2) {
            setFieldError('register-name', 'register-name-error', 'Please enter your full name (at least 2 characters).');
            isValid = false;
        } else {
            setFieldError('register-name', 'register-name-error', null);
        }

        // Email validation
        if (!email) {
            setFieldError('register-email', 'register-email-error', 'Please enter your email address.');
            isValid = false;
        } else if (!isValidEmail(email)) {
            setFieldError('register-email', 'register-email-error', 'Please enter a valid email address (e.g., name@example.com).');
            isValid = false;
        } else {
            setFieldError('register-email', 'register-email-error', null);
        }

        // Password validation
        if (!password) {
            setFieldError('register-password', 'register-password-error', 'Please enter a password.');
            isValid = false;
        } else if (password.length < 8) {
            setFieldError('register-password', 'register-password-error', 'Password must be at least 8 characters long.');
            isValid = false;
        } else {
            setFieldError('register-password', 'register-password-error', null);
        }

        // Confirm password validation
        if (!confirm) {
            setFieldError('register-confirm', 'register-confirm-error', 'Please confirm your password.');
            isValid = false;
        } else if (password !== confirm) {
            setFieldError('register-confirm', 'register-confirm-error', 'Passwords do not match. Please verify.');
            isValid = false;
        } else {
            setFieldError('register-confirm', 'register-confirm-error', null);
        }

        if (!isValid) {
            e.preventDefault();
            const firstError = form.querySelector('[aria-invalid="true"]');
            firstError?.focus();
            return false;
        }

        // Enter loading state
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.classList.add('loading');
        }
        return true;
    });
}

/**
 * Initialize Forgot Password Accessible Modal
 */
function initForgotPasswordModal() {
    const trigger = document.getElementById('link-forgot-password');
    const modalBackdrop = document.getElementById('forgot-password-modal');
    if (!trigger || !modalBackdrop) return;

    const closeBtns = modalBackdrop.querySelectorAll('[data-close-modal]');

    function openModal() {
        modalBackdrop.classList.add('active');
        modalBackdrop.setAttribute('aria-hidden', 'false');
        const firstFocusable = modalBackdrop.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        firstFocusable?.focus();
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        modalBackdrop.classList.remove('active');
        modalBackdrop.setAttribute('aria-hidden', 'true');
        trigger.focus();
        document.body.style.overflow = '';
    }

    trigger.addEventListener('click', (e) => {
        e.preventDefault();
        openModal();
    });

    closeBtns.forEach(btn => {
        btn.addEventListener('click', closeModal);
    });

    // Close on backdrop click
    modalBackdrop.addEventListener('click', (e) => {
        if (e.target === modalBackdrop) {
            closeModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modalBackdrop.classList.contains('active')) {
            closeModal();
        }
    });
}
