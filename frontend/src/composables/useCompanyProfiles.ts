import { ref } from 'vue';

export interface CompanyProfile {
    id: string;
    name: string;
    officialName: string;
    address: string;
    phone: string;
    registrationNumber: string;
    bankDetails: string;
    isDefault?: boolean;
}

// Global state for mock company profiles so it persists across page navigations
const profiles = ref<CompanyProfile[]>([
    {
        id: 'headquarters',
        name: '本社プロファイル',
        officialName: '株式会社TaxAgent',
        address: '〒150-0000\n東京都渋谷区xxxxx',
        phone: '03-0000-0000',
        registrationNumber: 'T-1234567890',
        bankDetails: '〇〇銀行 △△支店 普通 1234567 ｶ)ﾀｯｸｽｴｰｼﾞｪﾝﾄ',
        isDefault: true
    },
    {
        id: 'branch_a',
        name: '関西支社',
        officialName: '株式会社TaxAgent 関西支社',
        address: '〒530-0001\n大阪府大阪市北区梅田x-x-x',
        phone: '06-0000-0000',
        registrationNumber: 'T-1234567890',
        bankDetails: '〇〇銀行 関西支店 普通 7654321 ｶ)ﾀｯｸｽｴｰｼﾞｪﾝﾄ ｶﾝｻｲ'
    },
    {
        id: 'freelance',
        name: '個人・フリーランス名義',
        officialName: '山田 太郎',
        address: '〒160-0022\n東京都新宿区新宿x-x-x',
        phone: '090-0000-0000',
        registrationNumber: 'T-0987654321',
        bankDetails: '〇〇銀行 新宿支店 普通 1111111 ﾔﾏﾀﾞﾀﾛｳ'
    }
]);

export function useCompanyProfiles() {
    const getProfiles = () => profiles.value;

    const addProfile = (profile: Omit<CompanyProfile, 'id'>) => {
        const newProfile = {
            ...profile,
            id: `profile-${Date.now()}`
        };
        if (newProfile.isDefault) {
            profiles.value.forEach(p => p.isDefault = false);
        }
        profiles.value.push(newProfile);
    };

    const updateProfile = (id: string, updates: Partial<CompanyProfile>) => {
        if (updates.isDefault) {
            profiles.value.forEach(p => p.isDefault = false);
        }
        const index = profiles.value.findIndex(p => p.id === id);
        if (index !== -1) {
            profiles.value[index] = { ...profiles.value[index], ...updates };
        }
    };

    const deleteProfile = (id: string) => {
        profiles.value = profiles.value.filter(p => p.id !== id);
    };

    const formatProfileForTextarea = (profile: CompanyProfile) => {
        return `${profile.officialName}\n${profile.address}\nTEL: ${profile.phone}\n登録番号: ${profile.registrationNumber}`;
    };

    return {
        profiles,
        getProfiles,
        addProfile,
        updateProfile,
        deleteProfile,
        formatProfileForTextarea
    };
}
