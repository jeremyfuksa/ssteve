# Smart Reply Templates

This directory contains Smart Reply template definitions for SSTeVe's auto-populated proof-of-reception feature.

## Template Structure

Each template consists of two files:

1. **JSON metadata file** - Defines text field positions, fonts, colors, and formatting
2. **PNG base image** - Background image (320x256 for ScottieS1, 320x240 for Robot36)

## Bundled Templates

SSTeVe includes three default templates:

### 1. QSL Card (`qsl_card`)
Classic QSL card design with full contact information.
- **Default Mode:** ScottieS1 (320x256)
- **Fields:** Both callsigns, frequency, timestamp, SNR
- **Use Case:** Formal acknowledgments, contest logging

### 2. Monitor Frame (`monitor_frame`)
Monitor-style layout with compact info display.
- **Default Mode:** ScottieS1 (320x256)
- **Fields:** Callsigns, mode, frequency, SNR (bottom bar)
- **Use Case:** Quick replies during net operations

### 3. Minimal Badge (`minimal_badge`)
Clean, minimalist design for fast transmission.
- **Default Mode:** Robot36 (320x240, ~36 seconds)
- **Fields:** Callsigns, timestamp only
- **Use Case:** Field operations (POTA/SOTA), low-power contacts

## Creating Base Images

Base images should be created at the target SSTV mode resolution:
- **ScottieS1/MartinM1:** 320x256 pixels
- **Robot36:** 320x240 pixels

### Recommended Workflow

1. **Design in your image editor** (GIMP, Photoshop, Figma)
   - Use SSTeVe color palette for consistency:
     - Background: `#0D1016` (deep charcoal)
     - Accent 1: `#7CFF8A` (lime green)
     - Accent 2: `#F2B451` (amber)
     - Accent 3: `#5BD6E8` (cyan)
     - Text: `#FFFFFF` (white)

2. **Export as PNG with transparency** (if using overlays)
   - RGB mode (no alpha channel in final export)
   - 320x256 or 320x240 resolution
   - Save in this directory

3. **Create JSON metadata file**
   - Copy one of the existing templates
   - Update `name`, `base_image`, and `fields`
   - Test field positions with preview generation

### JSON Field Reference

```json
{
  "id": "callsign_received",       // Unique field identifier
  "label": "Their Callsign",        // Human-readable label (not rendered)
  "x": 50,                          // X position in pixels
  "y": 100,                         // Y position in pixels
  "font_size": 32,                  // Font size in points
  "font_family": "Arial",           // Font name (system font)
  "color": "#FFFFFF",               // Hex color code
  "alignment": "left",              // "left", "center", or "right"
  "format": "{value}"               // Optional Python format string
}
```

### Available Field IDs

Auto-populated from image metadata:
- `callsign_received` - Remote station's callsign *(required)*
- `callsign_operator` - Your callsign (from config)
- `frequency_mhz` - Frequency in MHz
- `timestamp_utc` - Contact timestamp (UTC)
- `snr_db` - Signal-to-noise ratio in dB
- `mode` - SSTV mode (ScottieS1, MartinM1, Robot36)
- `operator_name` - Remote operator's name (if available)

### Format Strings

Use Python format strings for field formatting:

```json
// Frequency with 3 decimal places
"format": "{value:.3f} MHz"

// Timestamp formatting
"format": "{value:%Y-%m-%d %H:%M UTC}"

// SNR with units
"format": "SNR: {value}dB"
```

## User Templates

Users can add custom templates to `~/.ssteve/templates/`:

1. Create template files (JSON + PNG)
2. Place in user templates directory
3. Templates are auto-discovered on app startup
4. Use `/smart_reply/reload_templates` endpoint to hot-reload

User templates override bundled templates with the same `template_id`.

## Testing Templates

Test your template with the API:

```bash
# List available templates
curl http://localhost:8000/api/v1/smart_reply/templates

# Generate preview
curl -X POST http://localhost:8000/api/v1/smart_reply/generate \
  -H "Content-Type: application/json" \
  -d '{
    "image_id": 1,
    "template_id": "qsl_card",
    "field_overrides": {
      "callsign_received": "W1AW",
      "frequency_mhz": 14.230
    }
  }'
```

## Design Guidelines

### SSTeVe Brand Voice

Templates should reflect SSTeVe's **friendly & nerdy** personality:
- Clean, professional layouts (not cluttered)
- Readable fonts at SSTV resolution
- High contrast for signal degradation
- Optional branding (not required)

### Accessibility

- Text size ≥ 14pt for readability after transmission
- 4.5:1 contrast ratio minimum (WCAG 2.1 AA)
- Clear hierarchy (large callsign, smaller metadata)

### Performance

- Robot36 templates (320x240) transmit in ~36 seconds
- ScottieS1 templates (320x256) transmit in ~110 seconds
- Prefer Robot36 for field operations
- Use ScottieS1 for high-quality acknowledgments

## Contributing Templates

To contribute templates to SSTeVe:

1. Create unique, original base images (CC0 or MIT license)
2. Test with real SSTV decoding (ensure readability)
3. Document your design rationale
4. Submit PR with template files + README update

---

**Need help?** Check the SSTeVe documentation or open an issue on GitHub.
