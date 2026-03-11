<script setup lang="ts">
import AdminSidebar from '@/components/layout/AdminSidebar.vue';
</script>

<template>
  <div class="min-h-screen bg-slate-50 flex">
    <!-- Sidebar -->
    <AdminSidebar />

    <!-- Main Content Area -->
    <main class="flex-1 ml-64 min-h-screen">
      <router-view />
    </main>
  </div>
</template>
