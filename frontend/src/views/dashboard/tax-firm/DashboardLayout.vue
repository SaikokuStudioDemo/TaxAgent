<script setup lang="ts">
import TaxFirmSidebar from '@/components/layout/TaxFirmSidebar.vue';
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex">
    <!-- Sidebar -->
    <TaxFirmSidebar />

    <!-- Main Content Area -->
    <main class="flex-1 ml-64 min-h-screen">
      <router-view />
    </main>
  </div>
</template>
