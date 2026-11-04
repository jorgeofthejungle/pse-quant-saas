import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: 'StockPilot PH TypeScript Web Portal',
    version: '2.0.0',
    environment: process.env.NODE_ENV,
  });
}
