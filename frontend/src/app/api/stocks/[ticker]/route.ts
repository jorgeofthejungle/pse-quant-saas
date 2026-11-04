import { NextRequest, NextResponse } from 'next/server';
import { getStockDetail } from '@/lib/db';

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ ticker: string }> }
) {
  const { ticker } = await context.params;

  try {
    const data = await getStockDetail(ticker);
    if (!data) {
      return NextResponse.json(
        { success: false, error: `Stock ${ticker} not found` },
        { status: 404 }
      );
    }
    return NextResponse.json({
      success: true,
      ticker: ticker.toUpperCase(),
      data,
    });
  } catch (err: any) {
    return NextResponse.json(
      { success: false, error: err.message || 'Failed to fetch stock detail' },
      { status: 500 }
    );
  }
}
