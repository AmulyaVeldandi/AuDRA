export interface SampleReport {
  id: string;
  name: string;
  text: string;
}

export const SAMPLE_REPORTS: SampleReport[] = [
  {
    id: "chest_ct_ggo",
    name: "Chest CT - Ground-glass nodule",
    text: `Examination: CT Chest without contrast
Findings: Ground-glass opacities in the right upper lobe measuring 12 mm.
Impression: Suggest follow-up imaging in 3 months to confirm resolution.`,
  },
  {
    id: "chest_ct_solid",
    name: "Chest CT - Solid nodule",
    text: `Examination: CT Chest with contrast
Findings: Solid pulmonary nodule in the left lower lobe measuring 8 mm.
Impression: Consider Fleischner 2017 guidelines for surveillance.`,
  },
  {
    id: "liver_mri_lesion",
    name: "Liver MRI - Hypervascular lesion",
    text: `Examination: MRI Abdomen with contrast
Findings: 1.5 cm hypervascular lesion in hepatic segment VIII.
Impression: Recommend dedicated follow-up based on ACR liver lesion guidelines.`,
  },
];
