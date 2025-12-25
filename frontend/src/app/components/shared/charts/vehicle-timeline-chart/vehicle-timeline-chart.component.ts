import { Component, ElementRef, Input, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BaseChartComponent } from '../base-chart.component';
import { ChartConfiguration } from 'chart.js';
import { TimelineData } from '../../../../models/video.model';

@Component({
  selector: 'app-vehicle-timeline-chart',
  templateUrl: './vehicle-timeline-chart.component.html',
  styleUrls: ['./vehicle-timeline-chart.component.css'],
  standalone: true,
  imports: [CommonModule]
})
export class VehicleTimelineChartComponent extends BaseChartComponent implements OnInit {
  @ViewChild('chartCanvas', { static: true }) chartCanvas!: ElementRef<HTMLCanvasElement>;
  @Input() set data(value: TimelineData | undefined) {
    if (value) {
      // Throttle at input level to prevent data accumulation
      this.throttledUpdate(() => this.addDataPoint(value));
    }
  }

  private readonly MAX_DATA_POINTS = 30;
  private timestamps: string[] = [];
  private totalVehiclesData: number[] = [];
  private speedingVehiclesData: number[] = [];

  ngOnInit(): void {
    const config: ChartConfiguration = {
      type: 'line',
      data: {
        labels: this.timestamps,
        datasets: [
          {
            label: 'Total Vehicles',
            data: this.totalVehiclesData,
            borderColor: 'rgb(75, 192, 192)',
            backgroundColor: 'rgba(75, 192, 192, 0.2)',
            tension: 0.4,
            fill: true,
            yAxisID: 'y'
          },
          {
            label: 'Speeding Vehicles',
            data: this.speedingVehiclesData,
            borderColor: 'rgb(255, 99, 132)',
            backgroundColor: 'rgba(255, 99, 132, 0.2)',
            tension: 0.4,
            fill: true,
            yAxisID: 'y'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 500
        },
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            display: true,
            position: 'top'
          },
          tooltip: {
            enabled: true
          },
          decimation: {
            enabled: true,
            algorithm: 'lttb',
            samples: 30
          }
        },
        scales: {
          x: {
            display: true,
            title: {
              display: true,
              text: 'Time'
            }
          },
          y: {
            display: true,
            position: 'left',
            title: {
              display: true,
              text: 'Vehicle Count'
            },
            beginAtZero: true
          }
        },
        elements: {
          point: {
            radius: 0,
            hitRadius: 10,
            hoverRadius: 5
          }
        }
      }
    };

    this.initChart(this.chartCanvas.nativeElement, config);
  }

  private addDataPoint(data: TimelineData): void {
    // Add new data
    this.timestamps.push(data.timestamp);
    this.totalVehiclesData.push(data.totalVehicles);
    this.speedingVehiclesData.push(data.speedingVehicles);

    // Remove oldest data if exceeds max points
    if (this.timestamps.length > this.MAX_DATA_POINTS) {
      this.timestamps.shift();
      this.totalVehiclesData.shift();
      this.speedingVehiclesData.shift();
    }

    this.updateChart();
  }
}
