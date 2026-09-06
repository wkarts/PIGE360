<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  modelValue: boolean | number | string | null | undefined;
  label?: string;
  disabled?: boolean;
}>(), {
  label: "",
  disabled: false,
});

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();

const checked = computed({
  get: () => props.modelValue === true || props.modelValue === 1 || props.modelValue === "1" || props.modelValue === "true",
  set: (value: boolean) => emit("update:modelValue", value),
});
</script>

<template>
  <label class="switch-field" :class="{ disabled }">
    <span class="switch-control">
      <input v-model="checked" class="switch-input" type="checkbox" :disabled="disabled" />
      <span class="switch-slider" aria-hidden="true" />
    </span>
    <span v-if="label" class="switch-label">{{ label }}</span>
  </label>
</template>
