# Flock Design System

Sistema de diseño para producto de tecnología e innovación. Handoff diseño + desarrollo · v1.1

Paleta púrpura de marca, neutrales entonados frío-cálido, y escalas consistentes de tipografía, espaciado, radios y elevación. Pila de fuente del sistema para máxima nitidez y rendimiento nativo.

---

## 1. Fundamentos

### Tokens de color (CSS variables)

Ver `../assets/tokens.css` para el bloque `:root` completo listo para pegar.

### Colores de marca

| Nombre        | Hex       | Uso |
|---------------|-----------|-----|
| Brand Purple  | `#7800C0` | Acción primaria, enlaces |
| Brand Dark    | `#300840` | Títulos, topbar, texto de contraste |
| Brand Bright  | `#9D2BD6` | Acentos, gradientes, bullets |
| Accent Orange | `#F85000` | Énfasis puntual / CTA secundario |

### Tintes y superficies

| Nombre     | Hex       | Uso |
|------------|-----------|-----|
| Soft       | `#f3e6fb` | Fondo de chips e íconos |
| Softer     | `#faf5fe` | Fondo de página |
| Surface    | `#f8f3fc` | Superficies sutiles, cabeceras de tabla |
| Panel / BG | `#ffffff` | Tarjetas, paneles, fondo base |

> **Regla de separación (contraste entre capas).** Las superficies escalonan en valor. Las tarjetas y paneles van sobre `Panel` (`#ffffff`), NUNCA sobre `Surface`/`Softer` (el mismo tinte del canvas) — violeta-sobre-violeta se ve plano y sin jerarquía. Si dos capas adyacentes comparten tinte, separalas: subí una a `Panel` o bajá el nav a una superficie oscura (`--nav-gradient`). Aprendizaje real de producto, no preferencia.

### Texto y bordes

| Nombre        | Hex       | Uso |
|---------------|-----------|-----|
| Text          | `#2c0b3a` | Texto principal |
| Text Soft     | `#6b5a78` | Texto secundario / descripciones |
| Text Faint    | `#9b8aa8` | Captions, placeholders, etiquetas |
| Border Strong | `#d9c7ec` | Bordes de inputs, divisores fuertes |
| Border        | `#e9ddf4` | Borde por defecto de tarjetas |

### Colores de estado

| Estado       | Fondo (bg) | Texto (fg) | Barra (bar) |
|--------------|-----------|-----------|-------------|
| Pendiente    | `#f1ecf6` | `#6b5a78` | `#9b8aa8`   |
| En progreso  | `#f3e6fb` | `#7800C0` | `#7800C0`   |
| Bloqueado    | `#fde7ee` | `#be123c` | `#e11d48`   |
| Completado   | `#dcf7e6` | `#15803d` | `#16a34a`   |

---

## 2. Tipografía

**Pila de fuente (cuerpo/UI):** `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`
**Pila mono (datos/números):** `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace` — usar con `font-variant-numeric: tabular-nums` (v1.1).

Base 14px · interlineado 1.45 · pesos 400–700 · titulares con tracking negativo.

| Nivel             | Tamaño  | Peso | Notas |
|-------------------|---------|------|-------|
| Display           | 30px    | 700  | letter-spacing -0.5px (v1.1: bajado de 800) |
| Título de sección | 20px    | 700  | v1.1: bajado de 800 |
| Título de tarjeta | 16.5px  | 700  | letter-spacing -0.2px (v1.1: bajado de 800) |
| Cuerpo            | 14px    | 400  | line-height 1.45 |
| Secundario        | 12.5px  | 500  | color text-soft |
| Etiqueta / Caption| 11px    | 700  | UPPERCASE, letter-spacing 0.7px |

---

## 3. Espaciado, radios y elevación

### Espaciado (base-4)

`4px · 8px · 12px · 16px · 20px · 24px · 32px · 40px`

Gaps más usados en la interfaz: 8, 12, 14, 18, 22, 26.

### Radios

| Radio  | Uso |
|--------|-----|
| `8px`  | Inputs, botones pequeños |
| `9px`  | Botones estándar |
| `12px` | Tarjetas (`--radius`) |
| `16px` | Modales |
| `18px` | Tarjetas de característica |
| `20px` | Pills / chips |
| `50%`  | Puntos de estado, avatares |

### Elevación

- **Base** — `0 1px 3px rgba(48,8,64,.08), 0 1px 2px rgba(48,8,64,.05)` (tarjetas)
- **Overlay** — `0 22px 50px -16px rgba(48,8,64,.42)` (modales, toasts)

---

## 4. Iconografía

Set de línea sobre grilla de **24px**, `stroke-width: 1.7`, extremos y uniones redondeados, `fill: none`, hereda `currentColor`.

```html
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
     stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <!-- paths -->
</svg>
```

Íconos incluidos: `trending`, `chip`, `experiment`, `share`, `compass`, `academy`, `progress`, `shield-check`, `team`, `billing`, más utilitarios (`plus`, `close`, `dots`).

---

## 5. Componentes

### Botones

```css
button {
  font-family: inherit; font-size: 13px; cursor: pointer;
  border: none; border-radius: 9px; padding: 9px 16px;
  font-weight: 600; display: inline-flex; align-items: center; gap: 7px;
  transition: transform .06s, background .15s;
}
button:active { transform: translateY(1px); }
```

| Variante   | Fondo | Texto | Hover |
|------------|-------|-------|-------|
| Primario   | `#7800C0` | `#fff` | `#650aa0` |
| Ghost      | `#fff` + borde `#d9c7ec` | `#2c0b3a` | fondo `#f8f3fc` |
| Acento     | `#F85000` | `#fff` | `#e04800` |
| Pequeño    | `#f3e6fb` | `#7800C0` | `#e9d4f7` · padding 6/12 · radio 8px |
| Light (sobre marca) | `rgba(255,255,255,.14)` | `#fff` | `rgba(255,255,255,.26)` |
| Contraste (sobre marca) | `#fff` | `#7800C0` | `#f3e6fb` |
| Icon button | transparente | `#9b8aa8` | fondo `#f3e6fb`, color `#7800C0` · 30×30, radio 6px |

### Campos de formulario

```css
label { font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: .5px; color: #9b8aa8; }

input, select {
  font-family: inherit; font-size: 13px; padding: 9px 11px;
  border: 1px solid #d9c7ec; border-radius: 8px;
  background: #fff; color: #2c0b3a;
}
input:focus, select:focus { outline: 2px solid #f3e6fb; border-color: #7800C0; }
```

Estructura: `.field` = columna con `gap: 6px` (label + control).

### Chips y badges

- **Status chip:** `font-size: 10.5px; font-weight: 700; padding: 3px 10px; border-radius: 20px;` con el par bg/fg del estado.
- **Meta pill:** `#f8f3fc` / `#6b5a78`, `padding: 3px 11px`.
- **Days badge:** `#f3e6fb` / `#7800C0`, `padding: 2px 8px`.
- **Sub-etiqueta:** `#f3e6fb` / `#7800C0`, peso 800, borde `1px solid rgba(120,0,192,.18)`.

### Tarjetas

- **Stat card** — `radius 12px`, sombra base, número 28px/800 en `#300840` + label con punto de color.
- **Feature card** — `radius 18px`, ícono 46px sobre `#f3e6fb`, badge, título 16.5px/800, borde superior de acento en hover (`transform: translateY(-4px)`).

### Overlays

- **Modal** — `max-width: 470px`, `radius 16px`, `--shadow-lg`, animación `pop` (scale .96→1). Estructura: `head` (título + cerrar) · `body` (`gap: 15px`) · `foot` (botones a la derecha). Fondo `rgba(48,8,64,.5)` con `backdrop-filter: blur(2px)`.
- **Toast** — fijo abajo-centro, `#300840` / `#fff`, `radius 10px`, `--shadow-lg`, auto-oculta ~1.9s.

```css
@keyframes pop { 0% { transform: scale(.96); opacity: 0; }
                 100% { transform: scale(1); opacity: 1; } }
```

---

## 6. Patrones

### Navegación por pestañas

```css
.tab { padding: 15px 18px; font-size: 14px; font-weight: 600;
       color: #6b5a78; border-bottom: 2px solid transparent; }
.tab.active { color: #300840; border-bottom-color: #7800C0; }
```

Contenedor sticky en `top: 0`, fondo blanco, borde inferior `#e9ddf4`.

### Barra de filtros

Panel blanco (`radius 12px`, sombra base) con fila de `.field` (`gap: 16px`, `align-items: flex-end`), spacer flexible y botón primario a la derecha.

### Tabla de datos

- Cabecera: fondo `#f8f3fc`, borde inferior `2px solid #d9c7ec`, labels 11px/700 UPPERCASE.
- Filas: `border-top: 1px solid #f3eefa`, celdas 13–13.5px, estado con status chip, valores numéricos alineados a la derecha en `#300840`/700.

### Cronograma (Gantt)

- Grilla `grid-template-columns: [label] repeat(n, 1fr)`.
- Cabecera de trimestres sobre `#f8f3fc`.
- Barras: `height 28px`, `radius 8px`, color por estado, texto blanco 11px/700, sombra `0 1px 2px rgba(48,8,64,.18)`; se posicionan con `grid-column`.
- Leyenda al pie con cuadros de color por estado.

---

## 7. Extensiones v1.1

Adiciones de nivel de marca (reutilizables en cualquier producto Flock). NO incluye tokens de dominio de una app concreta (etapas, outcomes, reglas de negocio).

### Dark theme

Activar con `html.dark`. Valores en `../assets/tokens.css`. Reglas clave:

- El morado de acción **brilla** en dark: `--brand` pasa de `#7800C0` a `#9D2BD6` (contraste sobre superficies oscuras). `--brand-dark` y `--accent` NO cambian.
- Superficies oscuras: `--bg #0d1117` · `--surface #161b22` · `--panel #1c2128`.
- Texto: `--text #e6edf3` · `--text-soft #8b949e` · `--text-faint #484f58`.
- Bordes translúcidos blancos (`.10` / `.16`). Sombras con `rgba(0,0,0,...)`.

### Tipografía mono para datos

Pila mono para números, tablas y contenido data-dense. Aplicar clase `.text-mono` (`font-family: var(--font-mono); font-variant-numeric: tabular-nums;`). Los números tabulan y alinean.

### Sidebar oscuro de marca

Navegación lateral con gradiente `--nav-gradient` = `linear-gradient(185deg, #300840 0%, #24062f 100%)`. Separa el nav del canvas claro; logo/isotipo en blanco (`flock-mark-white.svg`) arriba con `--brand-gradient`.

### Stat card con gradiente

Card destacada (hero KPI) con fondo `--stat-gradient` = `linear-gradient(135deg, #7800C0 0%, #9D2BD6 100%)`, texto blanco. En hover **subir brillo** (`filter: brightness(1.07)`), NUNCA virar a blanco. Clase `.stat-card-hero`.

---

## Activos

Logotipos incluidos en `../assets/` (SVG, fuente de verdad del producto):

- `flock-logo.svg` — logotipo completo púrpura (para fondos claros).
- `flock-mark.svg` — isotipo púrpura + naranja (fondos claros).
- `flock-mark-white.svg` — isotipo blanco (para fondos oscuros / topbar).

Nota: el logo usa `#7c2c8c` (púrpura) y `#fc441c` (naranja) — variantes propias de marca, NO idénticas a los tokens `--brand` / `--accent`. No sustituir los colores del logo por tokens.

El header usa un gradiente de marca: `linear-gradient(120deg, #300840 0%, #7800C0 100%)`.
