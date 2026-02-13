/**
 * ImageThumbnail - Clickable thumbnail with lightbox for generated images
 *
 * Renders a small preview that expands to full size on click.
 */

import React, { useState } from 'react';
import './ImageThumbnail.css';

interface ImageThumbnailProps {
  src: string;
  alt?: string;
  width?: number;
  height?: number;
  style?: string;
  purpose?: string;
  className?: string;
}

export const ImageThumbnail: React.FC<ImageThumbnailProps> = ({
  src,
  alt = 'Generated image',
  width,
  height,
  style,
  purpose,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  const handleOpen = () => setIsOpen(true);
  const handleClose = () => setIsOpen(false);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleClose();
    }
  };

  const handleImageLoad = () => setIsLoading(false);
  const handleImageError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  if (hasError) {
    return (
      <div className={`image-thumbnail error ${className}`}>
        <span className="error-icon">!</span>
        <span className="error-text">Image unavailable</span>
      </div>
    );
  }

  return (
    <>
      {/* Thumbnail */}
      <div
        className={`image-thumbnail ${className}`}
        onClick={handleOpen}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && handleOpen()}
        title="Click to expand"
      >
        {isLoading && <div className="thumbnail-loading">...</div>}
        <img
          src={src}
          alt={alt}
          onLoad={handleImageLoad}
          onError={handleImageError}
          style={{ display: isLoading ? 'none' : 'block' }}
        />
        <div className="thumbnail-overlay">
          <span className="expand-icon">+</span>
        </div>
        {(style || purpose) && (
          <div className="thumbnail-meta">
            {style && <span className="meta-style">{style}</span>}
            {purpose && <span className="meta-purpose">{purpose}</span>}
          </div>
        )}
      </div>

      {/* Lightbox */}
      {isOpen && (
        <div
          className="image-lightbox"
          onClick={handleClose}
          onKeyDown={handleKeyDown}
          role="dialog"
          aria-modal="true"
          tabIndex={-1}
        >
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <button className="lightbox-close" onClick={handleClose} title="Close">
              x
            </button>
            <img src={src} alt={alt} />
            <div className="lightbox-info">
              {alt && alt !== 'Generated image' && (
                <p className="lightbox-prompt">{alt}</p>
              )}
              <div className="lightbox-meta">
                {width && height && (
                  <span className="meta-dimensions">{width}x{height}</span>
                )}
                {style && <span className="meta-style">{style}</span>}
                {purpose && <span className="meta-purpose">{purpose}</span>}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

/**
 * Parse message content for generated image references
 * Returns array of image objects found in the text
 */
export interface ParsedImage {
  url: string;
  prompt?: string;
  style?: string;
  purpose?: string;
  width?: number;
  height?: number;
  imageId?: string;
}

export function parseImagesFromMessage(content: string): ParsedImage[] {
  const images: ParsedImage[] = [];

  // Pattern 1: Look for image paths in tool results
  // Matches: path: "/data/images/..." or "path": "/generated-images/..."
  const pathPattern = /["']?path["']?\s*[:=]\s*["']([^"']+\.(?:png|jpg|jpeg|webp))["']/gi;
  let match;
  while ((match = pathPattern.exec(content)) !== null) {
    const path = match[1];
    // Convert filesystem path to URL
    let url = path;
    if (path.includes('/data/images/')) {
      // Extract the part after /data/images/
      const relativePath = path.split('/data/images/')[1];
      url = `/generated-images/${relativePath}`;
    } else if (!path.startsWith('/generated-images') && !path.startsWith('http')) {
      // Assume it's a relative path from the images directory
      url = `/generated-images/${path}`;
    }

    // Try to extract additional metadata from nearby lines
    const styleMatch = content.match(/style:\s*["']([^"']+)["']/i);
    const purposeMatch = content.match(/purpose:\s*["']([^"']+)["']/i);
    const imageIdMatch = content.match(/image_id:\s*["']([^"']+)["']/i);
    const dimensionsMatch = content.match(/Dimensions:\s*(\d+)x(\d+)/i);

    images.push({
      url,
      style: styleMatch?.[1],
      purpose: purposeMatch?.[1],
      imageId: imageIdMatch?.[1],
      width: dimensionsMatch ? parseInt(dimensionsMatch[1]) : undefined,
      height: dimensionsMatch ? parseInt(dimensionsMatch[2]) : undefined,
    });
  }

  // Pattern 2: Look for image_id references
  const idPattern = /["']?image_id["']?\s*[:=]\s*["']([a-f0-9-]{36})["']/gi;
  while ((match = idPattern.exec(content)) !== null) {
    const imageId = match[1];
    // We'll need to fetch metadata for this - for now just store the ID
    images.push({ imageId, url: '' });
  }

  // Pattern 3: Look for generated-images URLs directly
  const urlPattern = /\/generated-images\/[^\s"'<>]+\.(?:png|jpg|jpeg|webp)/gi;
  while ((match = urlPattern.exec(content)) !== null) {
    const url = match[0];
    // Avoid duplicates
    if (!images.some(img => img.url === url)) {
      images.push({ url });
    }
  }

  // Pattern 4: Tool result JSON with image info
  // Look for structured results like {"success": true, "path": "...", "style": "..."}
  try {
    // Try to find JSON-like structures
    const jsonPattern = /\{[^{}]*"path"\s*:\s*"[^"]+\.(?:png|jpg|jpeg|webp)"[^{}]*\}/gi;
    while ((match = jsonPattern.exec(content)) !== null) {
      try {
        const jsonStr = match[0];
        const parsed = JSON.parse(jsonStr);
        if (parsed.path) {
          let url = parsed.path;
          if (url.includes('/data/images/')) {
            const relativePath = url.split('/data/images/')[1];
            url = `/generated-images/${relativePath}`;
          }
          images.push({
            url,
            prompt: parsed.prompt,
            style: parsed.style,
            purpose: parsed.purpose,
            width: parsed.width,
            height: parsed.height,
            imageId: parsed.image_id,
          });
        }
      } catch {
        // Not valid JSON, skip
      }
    }
  } catch {
    // Pattern matching failed, skip
  }

  // Deduplicate by URL
  const seen = new Set<string>();
  return images.filter(img => {
    if (!img.url || seen.has(img.url)) return false;
    seen.add(img.url);
    return true;
  });
}

export default ImageThumbnail;
