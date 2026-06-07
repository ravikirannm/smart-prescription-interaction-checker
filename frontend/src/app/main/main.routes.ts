import { Routes } from '@angular/router';
import { MainComponent } from './main.component';

export const routes: Routes = [
  {
    path: '',
    component: MainComponent,
    children: [
      { path: '', redirectTo: 'mydoc', pathMatch: 'full' },
      {
        path: 'mydoc',
        loadChildren: () => import('./mydoc/mydoc.module').then((m) => m.MydocModule),
      },
    ],
  },
];
