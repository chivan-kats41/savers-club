// Colours are CSS variables (so dark mode and theming work). Plain utilities (bg-muted) keep the
// simple var() — which works in every browser — while opacity variants (bg-muted/40) use color-mix().
const c = (name) => ({ opacityValue }) =>
  opacityValue === undefined || String(opacityValue).startsWith('var(') || opacityValue === '1'
    ? `var(--${name})`
    : `color-mix(in srgb, var(--${name}) calc(${opacityValue} * 100%), transparent)`;

module.exports = Object.assign({
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            background: c('background'),
            foreground: c('foreground'),
            card: { DEFAULT: c('card'), foreground: c('card-foreground') },
            popover: { DEFAULT: c('popover'), foreground: c('popover-foreground') },
            primary: { DEFAULT: c('primary'), foreground: c('primary-foreground'), soft: c('primary-soft') },
            secondary: { DEFAULT: c('secondary'), foreground: c('secondary-foreground'), soft: c('secondary-soft') },
            accent: { DEFAULT: c('accent'), foreground: c('accent-foreground'), soft: c('accent-soft') },
            muted: { DEFAULT: c('muted'), foreground: c('muted-foreground') },
            destructive: { DEFAULT: c('destructive'), foreground: c('destructive-foreground') },
            success: { DEFAULT: c('success'), foreground: c('success-foreground') },
            warning: { DEFAULT: c('warning'), foreground: c('warning-foreground') },
            border: c('border'),
            input: c('input'),
            ring: c('ring'),
            sidebar: {
              DEFAULT: c('sidebar'), foreground: c('sidebar-foreground'),
              primary: c('sidebar-primary'), 'primary-foreground': c('sidebar-primary-foreground'),
              accent: c('sidebar-accent'), 'accent-foreground': c('sidebar-accent-foreground'),
              border: c('sidebar-border'), ring: c('sidebar-ring'),
            },
            'chart-1': c('chart-1'), 'chart-2': c('chart-2'), 'chart-3': c('chart-3'),
            'chart-4': c('chart-4'), 'chart-5': c('chart-5'),
          },
          borderRadius: {
            sm: 'calc(var(--radius) - 4px)', md: 'calc(var(--radius) - 2px)', lg: 'var(--radius)',
            xl: 'calc(var(--radius) + 4px)', '2xl': 'calc(var(--radius) + 8px)', '3xl': 'calc(var(--radius) + 12px)',
          },
          fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
          boxShadow: { card: 'var(--shadow-card)' },
          borderColor: { DEFAULT: 'var(--border)' },
          ringColor: { DEFAULT: 'var(--ring)' },
        },
      },
    }, {content: ["./**/templates/**/*.html", "./hub/static/hub/js/*.js"]});
