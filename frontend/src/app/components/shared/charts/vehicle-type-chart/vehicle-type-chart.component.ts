import { Component, ElementRef, Input, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BaseChartComponent } from '../base-chart.component';
import { ChartConfiguration } from 'chart.js';
import { VehicleTypeData } from '../../../../models/video.model';

@Component({
  selector: 'app-vehicle-type-chart',
  templateUrl: './vehicle-type-chart.component.html',
  styleUrls: ['./vehicle-type-chart.component.css'],
  standalone: true,
  imports: [CommonModule]
})
export class VehicleTypeChartComponent extends BaseChartComponent implements OnInit {
  @ViewChild('chartCanvas', { static: true }) chartCanvas!: ElementRef<HTMLCanvasElement>;
  @Input() set data(value: VehicleTypeData | undefined) {
    if (value) {
      this.updateVehicleTypes(value);
    }
  }

  private vehicleTypes: string[] = [];
  private vehicleCounts: number[] = [];

  ngOnInit(): void {
    const config: ChartConfiguration = {
      type: 'doughnut',
      data: {
        labels: this.vehicleTypes,
        datasets: [{
          data: this.vehicleCounts,
          backgroundColor: [
            'rgba(255, 99, 132, 0.8)',
            'rgba(54, 162, 235, 0.8)',
            'rgba(255, 206, 86, 0.8)',
            'rgba(75, 192, 192, 0.8)',
            'rgba(153, 102, 255, 0.8)',
            'rgba(255, 159, 64, 0.8)'
          ],
          borderColor: [
            'rgba(255, 99, 132, 1)',
            'rgba(54, 162, 235, 1)',
            'rgba(255, 206, 86, 1)',
            'rgba(75, 192, 192, 1)',
            'rgba(153, 102, 255, 1)',
            'rgba(255, 159, 64, 1)'
          ],
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 500
        },
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: {
              padding: 15,
              font: {
                size: 12
              }
            }
          },
          tooltip: {
            enabled: true,
            callbacks: {
              label: (context) => {
                const label = context.label || '';
                const value = context.parsed || 0;
                const total = context.dataset.data.reduce((a: number, b: any) => a + (b as number), 0);
                const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
                return `${label}: ${value} (${percentage}%)`;
              }
            }
          }
        }
      }
    };

    this.initChart(this.chartCanvas.nativeElement, config);
  }

  private updateVehicleTypes(data: VehicleTypeData): void {
    this.throttledUpdate(() => {
      // Convert object to arrays
      this.vehicleTypes = Object.keys(data);
      this.vehicleCounts = Object.values(data);

      if (!this.chart) return;

      // Update chart data
      this.chart.data.labels = this.vehicleTypes;
      this.chart.data.datasets[0].data = this.vehicleCounts;

      this.updateChart();
    });
  }

  getTotalVehicles(): number {
    return this.vehicleCounts.reduce((a, b) => a + b, 0);
  }
}
