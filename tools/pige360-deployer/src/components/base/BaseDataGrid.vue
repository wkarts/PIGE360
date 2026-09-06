<script setup lang="ts">
defineProps<{ rows: Record<string, unknown>[]; columns: { key: string; label: string }[]; emptyText?: string }>();
</script>

<template>
  <div class="table-wrap data-grid-card">
    <table class="data-grid-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
          <th v-if="$slots.actions">Ações</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id ?? JSON.stringify(row))">
          <td v-for="column in columns" :key="column.key">{{ row[column.key] ?? '-' }}</td>
          <td v-if="$slots.actions"><slot name="actions" :row="row" /></td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + ($slots.actions ? 1 : 0)" class="empty-cell">{{ emptyText || 'Nenhum registro encontrado.' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
