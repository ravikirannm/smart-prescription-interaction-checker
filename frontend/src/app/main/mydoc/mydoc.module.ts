import { NgModule } from '@angular/core';
import { RouterModule } from '@angular/router';
import { MydocComponent } from './mydoc.component';
import { routes } from './mydoc.routes';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

@NgModule({
  declarations: [MydocComponent],
  imports: [
    RouterModule.forChild(routes),
    CommonModule,
    ReactiveFormsModule,
    FormsModule
],
})
export class MydocModule {}
