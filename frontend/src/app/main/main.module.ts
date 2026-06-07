import { NgModule } from '@angular/core';
import { RouterModule } from '@angular/router';
import { MainComponent } from './main.component';
import { routes } from './main.routes';

@NgModule({
  declarations: [MainComponent],
  imports: [RouterModule.forChild(routes)],
})
export class MainModule {}
