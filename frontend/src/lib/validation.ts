// Validation and sanitization utilities

// Limits
export const MAX_WORKSPACE_NAME_LENGTH = 100;
export const MAX_CSV_FILE_SIZE = 10 * 1024 * 1024; // 10MB
export const MAX_CUSTOMER_NAME_LENGTH = 200;

// Sanitize string to prevent XSS - strips HTML tags
export function sanitizeString(value: string): string {
  if (!value) return '';

  // Remove HTML tags
  const withoutTags = value.replace(/<[^>]*>/g, '');

  // Decode HTML entities to prevent double-encoding issues
  const textarea = document.createElement('textarea');
  textarea.innerHTML = withoutTags;
  const decoded = textarea.value;

  // Re-encode dangerous characters
  return decoded
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

// Validate workspace name
export function validateWorkspaceName(name: string): { valid: boolean; error?: string } {
  const trimmed = name.trim();

  if (!trimmed) {
    return { valid: false, error: 'Workspace name is required' };
  }

  if (trimmed.length > MAX_WORKSPACE_NAME_LENGTH) {
    return { valid: false, error: `Workspace name must be less than ${MAX_WORKSPACE_NAME_LENGTH} characters` };
  }

  // Check for suspicious patterns (basic SQL injection / script patterns)
  const suspiciousPatterns = [
    /<script/i,
    /javascript:/i,
    /on\w+=/i, // onclick=, onerror=, etc.
    /DROP\s+TABLE/i,
    /DELETE\s+FROM/i,
    /INSERT\s+INTO/i,
    /UNION\s+SELECT/i,
  ];

  for (const pattern of suspiciousPatterns) {
    if (pattern.test(trimmed)) {
      return { valid: false, error: 'Invalid characters in workspace name' };
    }
  }

  return { valid: true };
}

// Validate CSV file
export function validateCSVFile(file: File): { valid: boolean; error?: string } {
  if (!file) {
    return { valid: false, error: 'No file selected' };
  }

  // Check file extension
  if (!file.name.toLowerCase().endsWith('.csv')) {
    return { valid: false, error: 'Only CSV files are supported' };
  }

  // Check file size
  if (file.size > MAX_CSV_FILE_SIZE) {
    const maxSizeMB = MAX_CSV_FILE_SIZE / 1024 / 1024;
    return { valid: false, error: `File too large. Maximum size is ${maxSizeMB}MB` };
  }

  // Check MIME type (not always reliable but adds another layer)
  const validMimeTypes = ['text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel'];
  if (file.type && !validMimeTypes.includes(file.type)) {
    // Don't block, just warn - MIME types can be unreliable
    console.warn('Unexpected MIME type for CSV:', file.type);
  }

  return { valid: true };
}

// Parse CSV safely (handles quoted fields with commas)
export function parseCSV(text: string, maxRows: number = 100): {
  headers: string[];
  rows: Record<string, string>[];
  error?: string;
} {
  try {
    const lines = text.split(/\r?\n/).filter(line => line.trim());

    if (lines.length === 0) {
      return { headers: [], rows: [], error: 'CSV file is empty' };
    }

    // Parse header
    const headers = parseCSVLine(lines[0]).map(h => sanitizeString(h.trim()));

    if (headers.length === 0) {
      return { headers: [], rows: [], error: 'No headers found in CSV' };
    }

    // Parse rows (limit to maxRows for preview)
    const rows: Record<string, string>[] = [];
    const dataLines = lines.slice(1, maxRows + 1);

    for (const line of dataLines) {
      const values = parseCSVLine(line);
      const row: Record<string, string> = {};

      headers.forEach((header, i) => {
        // Sanitize each value
        row[header] = sanitizeString((values[i] || '').trim());
      });

      rows.push(row);
    }

    return { headers, rows };
  } catch (err) {
    return { headers: [], rows: [], error: 'Failed to parse CSV file' };
  }
}

// Parse a single CSV line, handling quoted fields
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (inQuotes) {
      if (char === '"') {
        if (nextChar === '"') {
          // Escaped quote
          current += '"';
          i++; // Skip next quote
        } else {
          // End of quoted field
          inQuotes = false;
        }
      } else {
        current += char;
      }
    } else {
      if (char === '"') {
        inQuotes = true;
      } else if (char === ',') {
        result.push(current);
        current = '';
      } else {
        current += char;
      }
    }
  }

  // Don't forget the last field
  result.push(current);

  return result;
}

// Extract email domain from email address
export function getEmailDomain(email: string): string | null {
  if (!email) return null;

  const match = email.match(/@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$/);
  return match ? match[1].toLowerCase() : null;
}

// Check if email domain is a common personal email provider
export function isPersonalEmailDomain(domain: string): boolean {
  const personalDomains = [
    'gmail.com',
    'yahoo.com',
    'hotmail.com',
    'outlook.com',
    'live.com',
    'icloud.com',
    'me.com',
    'aol.com',
    'mail.com',
    'protonmail.com',
    'proton.me',
  ];

  return personalDomains.includes(domain.toLowerCase());
}

// Generate a CSRF token for OAuth flows
export function generateCSRFToken(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
}

// Store and verify CSRF token
export function storeCSRFToken(token: string, provider: string): void {
  sessionStorage.setItem(`oauth_csrf_${provider}`, token);
}

export function verifyCSRFToken(token: string, provider: string): boolean {
  const stored = sessionStorage.getItem(`oauth_csrf_${provider}`);
  sessionStorage.removeItem(`oauth_csrf_${provider}`); // One-time use
  return stored === token;
}
