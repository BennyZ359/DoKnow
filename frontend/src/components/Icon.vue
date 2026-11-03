<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  graph: 'M9 3h6v5H9V3ZM2 16h6v5H2v-5Zm14 0h6v5h-6v-5ZM12 8v4M5 16v-4h14v4',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  download: 'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
  home: 'M3 10.5 12 3l9 7.5V21h-6v-7H9v7H3V10.5Z',
  book: 'M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1m0-15c3-2 6-2 9-1v15c-3-1-6-1-9 1V5Z',
  repeat: 'M20 7H7a4 4 0 0 0-4 4m17-4-4-4m4 4-4 4M4 17h13a4 4 0 0 0 4-4m-17 4 4 4m-4-4 4-4',
  notes: 'M5 3h14v18H5V3Zm4 5h6m-6 4h6m-6 4h4',
  settings:
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17m10-10 1.4-1.4',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  plus: 'M12 5v14M5 12h14',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12M6 18 18 6',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l3 2',
  sparkle: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6',
  search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  leaf: 'M20 3C8 3 3 8 4 14c1 5 6 7 10 3 4-4 6-9 6-14ZM4 21 16 9',
  menu: 'M4 6h16M4 12h16M4 18h16',
  message: 'M3 4h18v13H8l-5 4V4Zm5 5h8m-8 4h5',
  lock: 'M6 10h12v11H6V10Zm3 0V6a3 3 0 0 1 6 0v4',
  target: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 5a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0 4h.01',
  history: 'M3 11a9 9 0 1 1 2 7M3 5v6h6m3-4v5l4 2',
}
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.sparkle" />
  </svg>
</template>
