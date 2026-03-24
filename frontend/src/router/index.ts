import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '@/lib/firebase/config'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'home',
            component: () => import('@/views/TopPage.vue'),
            meta: { guestOnly: true }
        },
        {
            path: '/register/tax-firm',
            name: 'register-tax-firm',
            component: () => import('@/views/register/TaxFirmRegistration.vue')
        },
        {
            path: '/register/corporate',
            name: 'register-corporate',
            component: () => import('@/views/register/CorporateRegistration.vue')
        },
        {
            path: '/dashboard/tax-firm',
            component: () => import('@/views/dashboard/tax-firm/DashboardLayout.vue'),
            meta: { requiresAuth: true },
            children: [
                { path: '', name: 'dashboard-tax-firm-home', component: () => import('@/views/dashboard/tax-firm/TaxFirmDashboardPage.vue') },
                { path: 'customers', name: 'dashboard-tax-firm-customers', component: () => import('@/views/dashboard/tax-firm/CustomerListPage.vue') },
                { path: 'contract-edit', name: 'dashboard-tax-firm-contract-edit-new', component: () => import('@/views/dashboard/tax-firm/ContractEditPage.vue') },
                { path: 'contract-edit/:id', name: 'dashboard-tax-firm-contract-edit-id', component: () => import('@/views/dashboard/tax-firm/ContractEditPage.vue') },
                { path: 'settings/matching-rules', name: 'dashboard-tax-firm-settings-matching-rules', component: () => import('@/views/dashboard/corporate/settings/MatchingRulesPage.vue') },
                { path: 'settings/journal-rules', name: 'dashboard-tax-firm-settings-journal-rules', component: () => import('@/views/dashboard/corporate/settings/JournalRulesPage.vue') },
                { path: 'users', name: 'dashboard-tax-firm-users', component: () => import('@/views/dashboard/shared/UserManagementPage.vue') }
            ]
        },
        {
            path: '/dashboard/corporate',
            component: () => import('@/views/dashboard/corporate/DashboardLayout.vue'),
            meta: { requiresAuth: true },
            children: [
                { path: '', name: 'dashboard-corporate-home', component: () => import('@/views/dashboard/corporate/CorporateSummaryPage.vue') },
                { path: 'receipts/upload', name: 'dashboard-corporate-receipts-upload', component: () => import('@/views/dashboard/corporate/receipts/ReceiptUploadPage.vue') },
                { path: 'receipts/approvals', name: 'dashboard-corporate-receipts-approvals', component: () => import('@/views/dashboard/corporate/receipts/ApprovalDashboardPage.vue') },
                { path: 'receipts/matching', name: 'dashboard-corporate-receipts-matching', component: () => import('@/views/dashboard/corporate/receipts/MatchingPage.vue') },
                {
                    path: 'invoices/create',
                    name: 'dashboard-corporate-invoices-create',
                    component: () => import('@/views/dashboard/corporate/invoices/InvoiceCreatePage.vue'),
                    meta: { title: '請求書作成' }
                },
                {
                    path: 'invoices/new',
                    redirect: { name: 'dashboard-corporate-invoices-create' }
                },
                {
                    path: 'invoices/receive',
                    name: 'dashboard-corporate-invoices-receive',
                    component: () => import('@/views/dashboard/corporate/invoices/ReceivedInvoiceUploadPage.vue'),
                    meta: { title: '受領請求書アップロード' }
                },
                {
                    path: 'invoices/list',
                    name: 'dashboard-corporate-invoices-list',
                    component: () => import('@/views/dashboard/corporate/invoices/InvoiceListPage.vue'),
                    meta: { title: '請求書リスト' }
                },
                { 
                    path: 'invoices/approvals', 
                    name: 'dashboard-corporate-invoices-approvals', 
                    component: () => import('@/views/dashboard/corporate/invoices/InvoiceApprovalPage.vue'),
                    meta: { title: '受領請求書承認' }
                },
                { path: 'invoices/matching', name: 'dashboard-corporate-invoices-matching', component: () => import('@/views/dashboard/corporate/invoices/InvoiceMatchingPage.vue') },
                { path: 'banking/import', name: 'dashboard-corporate-banking-import', component: () => import('@/views/dashboard/corporate/banking/BankingImportPage.vue') },
                { path: 'rules/approvals', name: 'dashboard-corporate-rules-approvals', component: () => import('@/views/dashboard/corporate/rules/ApprovalRulesPage.vue') },
                { path: 'settings/organization', name: 'dashboard-corporate-settings-organization', component: () => import('@/views/dashboard/corporate/settings/OrganizationPage.vue') },
                { path: 'settings/company', name: 'dashboard-corporate-settings-company', component: () => import('@/views/dashboard/corporate/settings/CompanyProfilePage.vue') },
                { path: 'settings/clients', name: 'dashboard-corporate-settings-clients', component: () => import('@/views/dashboard/corporate/clients/ClientDirectoryPage.vue') },
                { path: 'settings/matching-rules', name: 'dashboard-corporate-settings-matching-rules', component: () => import('@/views/dashboard/corporate/settings/MatchingRulesPage.vue') },
                { path: 'settings/journal-rules', name: 'dashboard-corporate-settings-journal-rules', component: () => import('@/views/dashboard/corporate/settings/JournalRulesPage.vue') },
                { path: 'users', name: 'dashboard-corporate-users', component: () => import('@/views/dashboard/shared/UserManagementPage.vue') }
            ]
        },
        {
            path: '/dashboard/admin',
            component: () => import('@/views/dashboard/admin/DashboardLayout.vue'),
            meta: { requiresAuth: true },
            children: [
                { path: '', name: 'dashboard-admin-home', component: () => import('@/views/dashboard/admin/AdminDashboardPage.vue') }
            ]
        }
    ]
})

router.beforeEach(async (to, _from, next) => {
    const requiresAuth = to.matched.some(record => record.meta.requiresAuth);
    const isLocalBypass = localStorage.getItem('DEV_BYPASS_AUTH') === 'true';

    if (requiresAuth && !auth.currentUser && !isLocalBypass) {
        next('/');
    } else {
        next();
    }
});

export default router
