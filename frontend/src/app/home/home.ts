import { Component } from '@angular/core';
import { Icon } from '../icon';
import { FinancialPreview } from './financial-preview';

@Component({
  selector: 'app-home',
  imports: [Icon, FinancialPreview],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly features = [
    {
      number: '01',
      icon: 'wallet',
      title: 'Доходи та витрати',
      text: 'Розумійте, звідки надходять гроші та на що вони йдуть. Категорії допомагають побачити головне.',
    },
    {
      number: '02',
      icon: 'chart',
      title: 'Зрозуміла аналітика',
      text: 'Дивіться на фінанси в розрізі місяця: доходи, витрати й залишок, який можна заощадити.',
    },
    {
      number: '03',
      icon: 'target',
      title: 'Заощадження з метою',
      text: 'Визначайте суму та термін, фіксуйте внески й стежте, як ваша ціль стає ближчою.',
    },
    {
      number: '04',
      icon: 'branches',
      title: 'Погляд у майбутнє',
      text: 'Порівнюйте песимістичний, реалістичний та оптимістичний сценарії на основі своєї історії.',
    },
  ];
}
